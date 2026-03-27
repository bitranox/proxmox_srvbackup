"""Package list backup adapter — save installed packages from remote servers.

Captures the output of ``dpkg --get-selections`` (re-importable) and
``dpkg -l`` (human-readable with versions) from each server and saves
them as text files alongside configuration backups.
"""

from __future__ import annotations

import logging
from pathlib import Path

from proxmox_srvbackup.adapters.ssh.commands import (
    local_run,
    ssh_run,
)
from proxmox_srvbackup.domain.behaviors import (
    build_packages_filename,
    build_timestamp,
)
from proxmox_srvbackup.domain.models import ServerConfig

from .retention import apply_retention

logger = logging.getLogger(__name__)

_DPKG_SELECTIONS_CMD = "dpkg --get-selections"
_DPKG_LIST_CMD = "dpkg -l"


def _run_and_capture(
    server: ServerConfig,
    command: str,
    *,
    ssh_key: str,
    ssh_user: str,
    ssh_timeout: int,
) -> str:
    """Run a command locally or remotely and return its stdout."""
    if server.is_local:
        result = local_run(command)
    else:
        result = ssh_run(server.hostname, command, ssh_key=ssh_key, user=ssh_user, timeout=ssh_timeout)
    return result.stdout


def _save_package_dump(  # noqa: PLR0913
    server: ServerConfig,
    *,
    command: str,
    suffix: str,
    dest_dir: Path,
    timestamp: str,
    ssh_key: str,
    ssh_user: str,
    ssh_timeout: int,
    retention_count: int,
    dry_run: bool,
) -> None:
    """Capture one dpkg command and write the result to a text file."""
    filename = build_packages_filename(server.name, timestamp, suffix)
    dest_path = dest_dir / filename

    if dry_run:
        logger.info("[DRY-RUN] Would save %s from %s to %s", suffix, server.hostname, dest_path)
        return

    stdout = _run_and_capture(server, command, ssh_key=ssh_key, ssh_user=ssh_user, ssh_timeout=ssh_timeout)

    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path.write_text(stdout, encoding="utf-8")

    logger.info("Package %s for %s saved: %s", suffix, server.name, dest_path)

    apply_retention(dest_dir, pattern=f"packages_{suffix}_*.txt", keep=retention_count)


def backup_packages(  # noqa: PLR0913
    server: ServerConfig,
    *,
    backup_dir: Path,
    ssh_key: str,
    ssh_user: str = "root",
    ssh_timeout: int = 15,
    retention_count: int = 3,
    dry_run: bool = False,
) -> None:
    """Save installed package lists from a Proxmox server.

    Creates two files per run in ``{backup_dir}/{server.name}/configs/``:
    - ``packages_selections_<server>_<timestamp>.txt`` — ``dpkg --get-selections``
    - ``packages_list_<server>_<timestamp>.txt`` — ``dpkg -l``

    Args:
        server: Target server configuration.
        backup_dir: Base directory for backups.
        ssh_key: Path to SSH private key for this server.
        ssh_user: SSH user for remote connection.
        ssh_timeout: SSH connection timeout in seconds.
        retention_count: Number of package list files to retain per type.
        dry_run: If True, log actions without executing.

    Raises:
        SSHConnectionError: If SSH connection or dpkg command fails.
        RetentionError: If old package list files cannot be pruned.
    """
    timestamp = build_timestamp()
    dest_dir = backup_dir / server.name / "configs"

    for command, suffix in ((_DPKG_SELECTIONS_CMD, "selections"), (_DPKG_LIST_CMD, "list")):
        _save_package_dump(
            server,
            command=command,
            suffix=suffix,
            dest_dir=dest_dir,
            timestamp=timestamp,
            ssh_key=ssh_key,
            ssh_user=ssh_user,
            ssh_timeout=ssh_timeout,
            retention_count=retention_count,
            dry_run=dry_run,
        )

    logger.info("Package list backup for %s complete", server.name)


__all__ = ["backup_packages"]
