"""SSH command execution and file streaming.

Provides the infrastructure layer for executing commands on remote Proxmox
servers and streaming their output to local files. Also provides local
variants for self-backup scenarios.
"""

from __future__ import annotations

import logging
import subprocess  # nosec B404
from pathlib import Path

from proxmox_srvbackup.domain.errors import SSHConnectionError

logger = logging.getLogger(__name__)

_SSH_BASE_OPTS = [
    "-o",
    "StrictHostKeyChecking=accept-new",
    "-o",
    "BatchMode=yes",
]

_SSH_STREAM_OPTS = [
    "-o",
    "ServerAliveInterval=60",
    "-o",
    "ServerAliveCountMax=3",
]


def _build_ssh_cmd(  # noqa: PLR0913
    host: str,
    command: str,
    *,
    ssh_key: str,
    user: str,
    timeout: int,
    extra_opts: list[str] | None = None,
) -> list[str]:
    """Build the ssh command argument list."""
    cmd = [
        "ssh",
        "-i",
        ssh_key,
        "-o",
        f"ConnectTimeout={timeout}",
        *_SSH_BASE_OPTS,
        *(extra_opts or []),
        f"{user}@{host}",
        command,
    ]
    return cmd


def ssh_run(
    host: str,
    command: str,
    *,
    ssh_key: str,
    user: str = "root",
    timeout: int = 15,
) -> subprocess.CompletedProcess[str]:
    """Run a command on a remote host via SSH.

    Args:
        host: Remote hostname or IP.
        command: Shell command to execute remotely.
        ssh_key: Path to the SSH private key file.
        user: Remote user (default: root).
        timeout: SSH connection timeout in seconds.

    Returns:
        CompletedProcess with stdout/stderr captured.

    Raises:
        SSHConnectionError: If SSH connection or remote command fails.
    """
    cmd = _build_ssh_cmd(host, command, ssh_key=ssh_key, user=user, timeout=timeout)
    logger.debug("ssh_run: %s@%s: %s", user, host, command)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)  # noqa: S603  # nosec B603
    except OSError as exc:
        raise SSHConnectionError(f"SSH to {host} failed: {exc}") from exc

    if result.returncode != 0:
        raise SSHConnectionError(f"SSH command on {host} exited with code {result.returncode}: {result.stderr.strip()}")
    return result


def ssh_pipe_to_file(  # noqa: PLR0913
    host: str,
    command: str,
    local_path: Path,
    *,
    ssh_key: str,
    user: str = "root",
    timeout: int = 15,
) -> None:
    """Stream remote command stdout to a local file via SSH.

    Opens an SSH connection, runs the command on the remote host, and writes
    its stdout directly to a local file. No intermediate temp files are
    created on the remote server.

    Args:
        host: Remote hostname or IP.
        command: Shell command whose stdout will be captured.
        local_path: Local file path to write the stream to.
        ssh_key: Path to the SSH private key file.
        user: Remote user (default: root).
        timeout: SSH connection timeout in seconds.

    Raises:
        SSHConnectionError: If SSH connection fails or remote command exits non-zero.
    """
    cmd = _build_ssh_cmd(
        host,
        command,
        ssh_key=ssh_key,
        user=user,
        timeout=timeout,
        extra_opts=_SSH_STREAM_OPTS,
    )
    logger.debug("ssh_pipe_to_file: %s@%s: %s -> %s", user, host, command, local_path)

    local_path.parent.mkdir(parents=True, exist_ok=True)

    with local_path.open("wb") as fh:
        try:
            proc = subprocess.Popen(cmd, stdout=fh, stderr=subprocess.PIPE)  # noqa: S603  # nosec B603
            _, stderr = proc.communicate()
        except OSError as exc:
            raise SSHConnectionError(f"SSH pipe to {host} failed: {exc}") from exc

    if proc.returncode != 0:
        local_path.unlink(missing_ok=True)
        raise SSHConnectionError(
            f"SSH pipe from {host} exited with code {proc.returncode}: {stderr.decode(errors='replace').strip()}"
        )


def local_run(command: str) -> subprocess.CompletedProcess[str]:
    """Run a command locally via shell.

    Used for self-backup when the backup server backs up its own data.

    Args:
        command: Shell command to execute.

    Returns:
        CompletedProcess with stdout/stderr captured.

    Raises:
        SSHConnectionError: If the command fails (reuses exception type for consistency).
    """
    logger.debug("local_run: %s", command)

    try:
        result = subprocess.run(  # noqa: S602  # nosec B602
            command,
            shell=True,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise SSHConnectionError(f"Local command failed: {exc}") from exc

    if result.returncode != 0:
        raise SSHConnectionError(f"Local command exited with code {result.returncode}: {result.stderr.strip()}")
    return result


def local_pipe_to_file(command: str, local_path: Path) -> None:
    """Pipe local command stdout to a file.

    Used for self-backup when the backup server backs up its own data.

    Args:
        command: Shell command whose stdout will be captured.
        local_path: Local file path to write the stream to.

    Raises:
        SSHConnectionError: If the command fails.
    """
    logger.debug("local_pipe_to_file: %s -> %s", command, local_path)

    local_path.parent.mkdir(parents=True, exist_ok=True)

    with local_path.open("wb") as fh:
        try:
            proc = subprocess.Popen(  # noqa: S602  # nosec B602
                command,
                shell=True,
                stdout=fh,
                stderr=subprocess.PIPE,
            )
            _, stderr = proc.communicate()
        except OSError as exc:
            raise SSHConnectionError(f"Local pipe failed: {exc}") from exc

    if proc.returncode != 0:
        local_path.unlink(missing_ok=True)
        raise SSHConnectionError(
            f"Local pipe exited with code {proc.returncode}: {stderr.decode(errors='replace').strip()}"
        )


__all__ = [
    "local_pipe_to_file",
    "local_run",
    "ssh_pipe_to_file",
    "ssh_run",
]
