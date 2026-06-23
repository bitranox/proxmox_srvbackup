"""In-memory backup adapters for testing.

Provides no-op implementations of backup ports that record calls
without performing any I/O.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from proxmox_srvbackup.domain.enums import BackupType
from proxmox_srvbackup.domain.models import BackupResult, BackupSummary, ServerConfig

if TYPE_CHECKING:
    from lib_layered_config import Config


def backup_config_in_memory(
    server: ServerConfig,
    *,
    backup_dir: Path,
    config_paths: Sequence[str],
    exclude_patterns: Sequence[str],
    ssh_key: str,
    ssh_user: str = "root",
    ssh_timeout: int = 15,
    retention_count: int = 3,
    dry_run: bool = False,
) -> None:
    """No-op config backup for testing."""


def backup_zfs_in_memory(
    server: ServerConfig,
    *,
    backup_dir: Path,
    ssh_key: str,
    ssh_user: str = "root",
    ssh_timeout: int = 15,
    retention_count: int = 3,
    dry_run: bool = False,
) -> None:
    """No-op ZFS backup for testing."""


def apply_retention_in_memory(directory: Path, *, pattern: str = "*", keep: int = 3) -> list[Path]:
    """No-op retention for testing."""
    return []


def setup_keys_in_memory(
    servers: Sequence[ServerConfig],
    *,
    key_dir: Path,
    key_prefix: str,
    bootstrap_key: str,
    authorized_keys_path: str = "/etc/pve/priv/authorized_keys",
) -> dict[str, bool]:
    """No-op key setup for testing — reports all servers as successful."""
    return {s.name: True for s in servers}


def backup_all_in_memory(
    servers: Sequence[ServerConfig],
    *,
    config: Config,
    backup_types: BackupType = BackupType.ALL,
    max_parallel: int = 4,
    dry_run: bool = False,
) -> BackupSummary:
    """No-op backup orchestration for testing — reports all servers as successful."""
    results = tuple(
        BackupResult(
            server=s.name,
            config_ok=s.backup_configfiles,
            config_skipped=not s.backup_configfiles,
            zfs_ok=s.backup_snapshot,
            zfs_skipped=not s.backup_snapshot,
            duration_seconds=0.1,
        )
        for s in servers
    )
    return BackupSummary(results=results, total_duration_seconds=0.1)


def backup_server_in_memory(
    server: ServerConfig,
    *,
    config: Config,
    backup_types: BackupType = BackupType.ALL,
    dry_run: bool = False,
) -> BackupResult:
    """No-op single server backup for testing."""
    return BackupResult(
        server=server.name,
        config_ok=server.backup_configfiles,
        config_skipped=not server.backup_configfiles,
        zfs_ok=server.backup_snapshot,
        zfs_skipped=not server.backup_snapshot,
        duration_seconds=0.1,
    )


__all__ = [
    "apply_retention_in_memory",
    "backup_all_in_memory",
    "backup_config_in_memory",
    "backup_server_in_memory",
    "backup_zfs_in_memory",
    "setup_keys_in_memory",
]
