"""ZFS rpool snapshot backup adapter — pull ZFS streams from remote servers.

Connects to a remote Proxmox server via SSH, creates a recursive ZFS
snapshot, streams it back compressed, and cleans up the remote snapshot.
"""

from __future__ import annotations

import logging
from pathlib import Path

from proxmox_srvbackup.adapters.ssh.commands import (
    local_pipe_to_file,
    local_run,
    ssh_pipe_to_file,
    ssh_run,
)
from proxmox_srvbackup.domain.behaviors import (
    build_snapshot_filename,
    build_snapshot_tag,
    build_timestamp,
)
from proxmox_srvbackup.domain.errors import SnapshotError, SSHConnectionError
from proxmox_srvbackup.domain.models import ServerConfig

from .retention import apply_retention

logger = logging.getLogger(__name__)


def _run_cmd(server: ServerConfig, command: str, *, ssh_key: str, ssh_user: str, ssh_timeout: int) -> None:
    """Run a command locally or remotely depending on server config."""
    if server.is_local:
        local_run(command)
    else:
        ssh_run(server.hostname, command, ssh_key=ssh_key, user=ssh_user, timeout=ssh_timeout)


def _pipe_cmd(  # noqa: PLR0913
    server: ServerConfig,
    command: str,
    local_path: Path,
    *,
    ssh_key: str,
    ssh_user: str,
    ssh_timeout: int,
) -> None:
    """Pipe command output to file locally or remotely."""
    if server.is_local:
        local_pipe_to_file(command, local_path)
    else:
        ssh_pipe_to_file(
            server.hostname,
            command,
            local_path,
            ssh_key=ssh_key,
            user=ssh_user,
            timeout=ssh_timeout,
        )


def _cleanup_stale_snapshots(
    server: ServerConfig,
    *,
    ssh_key: str,
    ssh_user: str,
    ssh_timeout: int,
) -> None:
    """Remove leftover pull_backup_* snapshots from previous failed runs."""
    list_cmd = "zfs list -H -t snapshot -o name | grep '@pull_backup_' || true"
    try:
        if server.is_local:
            result = local_run(list_cmd)
        else:
            result = ssh_run(server.hostname, list_cmd, ssh_key=ssh_key, user=ssh_user, timeout=ssh_timeout)

        stale_snapshots = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        for snap in stale_snapshots:
            logger.warning("Cleaning up stale snapshot: %s on %s", snap, server.name)
            destroy_cmd = f"zfs destroy -r {snap}"
            _run_cmd(server, destroy_cmd, ssh_key=ssh_key, ssh_user=ssh_user, ssh_timeout=ssh_timeout)
    except SSHConnectionError:
        logger.warning("Could not check for stale snapshots on %s", server.name)


def backup_zfs(  # noqa: PLR0913
    server: ServerConfig,
    *,
    backup_dir: Path,
    ssh_key: str,
    ssh_user: str = "root",
    ssh_timeout: int = 15,
    retention_count: int = 3,
    dry_run: bool = False,
) -> None:
    """Pull ZFS rpool snapshot from a Proxmox server.

    Steps:
        1. Clean up stale snapshots from previous failed runs.
        2. Create a recursive ZFS snapshot on the remote server.
        3. Stream ``zfs send -R`` compressed with gzip to a local file.
        4. Destroy the remote snapshot (always, even on failure via finally).
        5. Apply retention policy to local snapshot directory.

    Args:
        server: Target server configuration.
        backup_dir: Base directory for backups.
        ssh_key: Path to SSH private key for this server.
        ssh_user: SSH user for remote connection.
        ssh_timeout: SSH connection timeout in seconds.
        retention_count: Number of snapshot files to retain.
        dry_run: If True, log actions without executing.

    Raises:
        SnapshotError: If snapshot creation or transfer fails.
        RetentionError: If old snapshot files cannot be pruned.
    """
    timestamp = build_timestamp()
    snap_tag = build_snapshot_tag(timestamp)
    full_snap = f"{server.zfs_pool}@{snap_tag}"
    filename = build_snapshot_filename(server.name, server.zfs_pool, timestamp)
    dest_dir = backup_dir / server.name / "snapshots"
    dest_path = dest_dir / filename

    if dry_run:
        logger.info("[DRY-RUN] Would backup ZFS from %s to %s", server.hostname, dest_path)
        logger.info("[DRY-RUN] Snapshot: %s", full_snap)
        logger.info("[DRY-RUN] Command: zfs send -R %s | gzip -1", full_snap)
        return

    logger.info("Starting ZFS backup for %s", server.name)

    _cleanup_stale_snapshots(server, ssh_key=ssh_key, ssh_user=ssh_user, ssh_timeout=ssh_timeout)

    snapshot_created = False
    try:
        create_cmd = f"zfs snapshot -r {full_snap}"
        logger.info("Creating snapshot: %s on %s", full_snap, server.name)
        try:
            _run_cmd(server, create_cmd, ssh_key=ssh_key, ssh_user=ssh_user, ssh_timeout=ssh_timeout)
        except SSHConnectionError as exc:
            raise SnapshotError(f"Snapshot creation failed on {server.name}: {exc}") from exc
        snapshot_created = True

        send_cmd = f"zfs send -R {full_snap} | gzip -1"
        logger.info("Streaming ZFS snapshot from %s to %s", server.name, dest_path)
        try:
            _pipe_cmd(
                server,
                send_cmd,
                dest_path,
                ssh_key=ssh_key,
                ssh_user=ssh_user,
                ssh_timeout=ssh_timeout,
            )
        except SSHConnectionError as exc:
            raise SnapshotError(f"Snapshot transfer failed from {server.name}: {exc}") from exc

        file_size = dest_path.stat().st_size
        logger.info(
            "ZFS backup for %s complete: %s (%.1f MB)",
            server.name,
            dest_path,
            file_size / 1_048_576,
        )
    finally:
        if snapshot_created:
            destroy_cmd = f"zfs destroy -r {full_snap}"
            logger.info("Destroying snapshot: %s on %s", full_snap, server.name)
            try:
                _run_cmd(server, destroy_cmd, ssh_key=ssh_key, ssh_user=ssh_user, ssh_timeout=ssh_timeout)
            except SSHConnectionError:
                logger.error("Failed to destroy snapshot %s on %s", full_snap, server.name)

    apply_retention(dest_dir, pattern="*_snapshot_*.zfs.gz", keep=retention_count)


__all__ = ["backup_zfs"]
