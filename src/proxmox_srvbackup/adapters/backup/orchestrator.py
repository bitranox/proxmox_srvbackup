"""Backup orchestration — parallel execution across multiple servers.

Coordinates backup operations for all configured Proxmox servers using a
thread pool for concurrent execution.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from proxmox_srvbackup.domain.enums import BackupType
from proxmox_srvbackup.domain.models import BackupResult, BackupSummary, ServerConfig

from .config_backup import backup_config
from .packages_backup import backup_packages
from .zfs_backup import backup_zfs

if TYPE_CHECKING:
    from lib_layered_config import Config

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class BackupSettings:
    """Parsed backup settings extracted from layered config.

    Eliminates raw dict access by providing typed fields for all
    backup-related configuration values.
    """

    backup_base_dir: Path
    max_parallel: int
    retention_count: int
    ssh_user: str
    ssh_connect_timeout: int
    ssh_key_dir: str
    ssh_key_prefix: str
    bootstrap_key: str = ""
    authorized_keys_path: str = "/etc/pve/priv/authorized_keys"
    config_paths: list[str] = field(default_factory=list[str])
    exclude_patterns: list[str] = field(default_factory=list[str])


def _resolve_ssh_key(server: ServerConfig, key_dir: str, key_prefix: str) -> str:
    """Return the SSH key path for a server."""
    return str(Path(key_dir) / f"{key_prefix}_{server.name}")


def extract_backup_settings(config: Config) -> BackupSettings:
    """Extract backup-related settings from layered config."""
    backup_cfg = config.get("backup", {})
    config_paths_section = backup_cfg.get("config_paths", {})
    return BackupSettings(
        backup_base_dir=Path(backup_cfg.get("backup_base_dir", "/mnt/zpool-ssd/px-node-backups")),
        max_parallel=int(backup_cfg.get("max_parallel", 4)),
        retention_count=int(backup_cfg.get("retention_count", 3)),
        ssh_user=str(backup_cfg.get("ssh_user", "root")),
        ssh_connect_timeout=int(backup_cfg.get("ssh_connect_timeout", 15)),
        ssh_key_dir=str(backup_cfg.get("ssh_key_dir", "/root/.ssh")),
        ssh_key_prefix=str(backup_cfg.get("ssh_key_prefix", "backup_pull")),
        bootstrap_key=str(backup_cfg.get("bootstrap_key", "")),
        authorized_keys_path=str(backup_cfg.get("authorized_keys_path", "/etc/pve/priv/authorized_keys")),
        config_paths=list[str](config_paths_section.get("paths", [])),
        exclude_patterns=list[str](config_paths_section.get("exclude_patterns", [])),
    )


def backup_server(
    server: ServerConfig,
    *,
    config: Config,
    backup_types: BackupType = BackupType.ALL,
    dry_run: bool = False,
) -> BackupResult:
    """Run backup for a single server and return the result.

    Args:
        server: Target server configuration.
        config: Application configuration.
        backup_types: Which backup types to perform.
        dry_run: If True, log actions without executing.

    Returns:
        BackupResult with status of each backup type.
    """
    settings = extract_backup_settings(config)
    ssh_key = _resolve_ssh_key(server, settings.ssh_key_dir, settings.ssh_key_prefix)

    start = time.monotonic()
    config_ok = True
    config_error = ""
    config_skipped = False
    zfs_ok = True
    zfs_error = ""
    zfs_skipped = False

    want_config = backup_types in (BackupType.ALL, BackupType.CONFIG)
    want_zfs = backup_types in (BackupType.ALL, BackupType.ZFS)

    if want_config and server.backup_configfiles:
        try:
            backup_config(
                server,
                backup_dir=settings.backup_base_dir,
                config_paths=settings.config_paths,
                exclude_patterns=settings.exclude_patterns,
                ssh_key=ssh_key,
                ssh_user=settings.ssh_user,
                ssh_timeout=settings.ssh_connect_timeout,
                retention_count=settings.retention_count,
                dry_run=dry_run,
            )
        except Exception as exc:
            config_ok = False
            config_error = str(exc)
            logger.error("Config backup failed for %s: %s", server.name, exc)

        try:
            backup_packages(
                server,
                backup_dir=settings.backup_base_dir,
                ssh_key=ssh_key,
                ssh_user=settings.ssh_user,
                ssh_timeout=settings.ssh_connect_timeout,
                retention_count=settings.retention_count,
                dry_run=dry_run,
            )
        except Exception as exc:
            logger.warning("Package list backup failed for %s: %s", server.name, exc)
    elif not server.backup_configfiles:
        config_skipped = True
        logger.info("Config backup disabled for %s (backup_configfiles=false)", server.name)

    if want_zfs and server.backup_snapshot:
        try:
            backup_zfs(
                server,
                backup_dir=settings.backup_base_dir,
                ssh_key=ssh_key,
                ssh_user=settings.ssh_user,
                ssh_timeout=settings.ssh_connect_timeout,
                retention_count=settings.retention_count,
                dry_run=dry_run,
            )
        except Exception as exc:
            zfs_ok = False
            zfs_error = str(exc)
            logger.error("ZFS backup failed for %s: %s", server.name, exc)
    elif not server.backup_snapshot:
        zfs_skipped = True
        logger.info("ZFS backup disabled for %s (backup_snapshot=false)", server.name)

    duration = time.monotonic() - start

    return BackupResult(
        server=server.name,
        config_ok=config_ok,
        config_error=config_error,
        config_skipped=config_skipped,
        zfs_ok=zfs_ok,
        zfs_error=zfs_error,
        zfs_skipped=zfs_skipped,
        duration_seconds=duration,
    )


def backup_all(
    servers: Sequence[ServerConfig],
    *,
    config: Config,
    backup_types: BackupType = BackupType.ALL,
    max_parallel: int = 4,
    dry_run: bool = False,
) -> BackupSummary:
    """Orchestrate backups across all configured servers.

    Uses a thread pool for parallel execution. Each server backup is
    independent and produces its own BackupResult.

    Args:
        servers: List of server configurations.
        config: Application configuration.
        backup_types: Which backup types to perform.
        max_parallel: Maximum number of concurrent backup operations.
        dry_run: If True, log actions without executing.

    Returns:
        BackupSummary with aggregated results.
    """
    start = time.monotonic()
    logger.info(
        "Starting backup for %d servers (max_parallel=%d, types=%s, dry_run=%s)",
        len(servers),
        max_parallel,
        backup_types.value,
        dry_run,
    )

    results: list[BackupResult] = []

    with ThreadPoolExecutor(max_workers=max_parallel) as executor:
        futures = {
            executor.submit(
                backup_server,
                server,
                config=config,
                backup_types=backup_types,
                dry_run=dry_run,
            ): server
            for server in servers
        }

        for future in as_completed(futures):
            server = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                logger.error("Unexpected error backing up %s: %s", server.name, exc)
                result = BackupResult(
                    server=server.name,
                    config_error=str(exc),
                    zfs_error=str(exc),
                    duration_seconds=0.0,
                )
            results.append(result)

    total_duration = time.monotonic() - start
    results.sort(key=lambda r: r.server)

    summary = BackupSummary(results=tuple(results), total_duration_seconds=total_duration)

    if summary.all_ok:
        logger.info("All %d server backups completed successfully in %.1fs", len(results), total_duration)
    else:
        failed = summary.failed_servers
        logger.warning(
            "%d of %d server backups failed in %.1fs",
            len(failed),
            len(results),
            total_duration,
        )

    return summary


__all__ = ["BackupSettings", "backup_all", "backup_server", "extract_backup_settings"]
