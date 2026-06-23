"""Configuration backup adapter — pull config archives from remote servers.

Connects to a remote Proxmox server via SSH, creates a tar archive of
configuration files on the fly, and streams it directly to a local file.
No temporary files are created on the remote server.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path

from proxmox_srvbackup.adapters.ssh.commands import (
    local_pipe_to_file,
    ssh_pipe_to_file,
)
from proxmox_srvbackup.domain.behaviors import (
    build_config_filename,
    build_timestamp,
)
from proxmox_srvbackup.domain.models import ServerConfig

from .retention import apply_retention

logger = logging.getLogger(__name__)


def _build_tar_command(config_paths: Sequence[str], exclude_patterns: Sequence[str]) -> str:
    """Build the remote tar command string."""
    excludes = " ".join(f"--exclude={p}" for p in exclude_patterns)
    paths = " ".join(config_paths)
    return f"tar --hard-dereference --ignore-failed-read -czf - {excludes} {paths} 2>/dev/null"


def backup_config(  # noqa: PLR0913
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
    """Pull configuration backup from a Proxmox server.

    Streams a tar archive of configuration files from the remote server
    directly to a local file via SSH pipe.

    Args:
        server: Target server configuration.
        backup_dir: Base directory for backups (e.g. /mnt/zpool-ssd/px-node-backups).
        config_paths: Paths to include in the tar archive.
        exclude_patterns: Paths to exclude from the tar archive.
        ssh_key: Path to SSH private key for this server.
        ssh_user: SSH user for remote connection.
        ssh_timeout: SSH connection timeout in seconds.
        retention_count: Number of backup files to retain.
        dry_run: If True, log actions without executing.

    Raises:
        SSHConnectionError: If SSH connection or tar command fails.
        RetentionError: If old backup files cannot be pruned.
    """
    timestamp = build_timestamp()
    filename = build_config_filename(server.name, timestamp)
    dest_dir = backup_dir / server.name / "configs"
    dest_path = dest_dir / filename
    tar_cmd = _build_tar_command(config_paths, exclude_patterns)

    if dry_run:
        logger.info("[DRY-RUN] Would backup config from %s to %s", server.hostname, dest_path)
        logger.info("[DRY-RUN] Remote command: %s", tar_cmd)
        return

    logger.info("Backing up config from %s to %s", server.hostname, dest_path)

    if server.is_local:
        local_pipe_to_file(tar_cmd, dest_path)
    else:
        ssh_pipe_to_file(
            server.hostname,
            tar_cmd,
            dest_path,
            ssh_key=ssh_key,
            user=ssh_user,
            timeout=ssh_timeout,
        )

    file_size = dest_path.stat().st_size
    logger.info("Config backup for %s complete: %s (%.1f MB)", server.name, dest_path, file_size / 1_048_576)

    apply_retention(dest_dir, pattern="backup_config_*.tar.gz", keep=retention_count)


__all__ = ["backup_config"]
