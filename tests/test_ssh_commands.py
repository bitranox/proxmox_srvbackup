"""Unit tests for ssh/commands.py — SSH and local command execution.

Tests mock subprocess.run/Popen to verify command construction,
error handling, file creation, and cleanup without real SSH connections.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from proxmox_srvbackup.adapters.ssh.commands import (
    local_pipe_to_file,
    local_run,
    ssh_pipe_to_file,
    ssh_run,
)
from proxmox_srvbackup.domain.errors import SSHConnectionError

# ---------------------------------------------------------------------------
# ssh_run
# ---------------------------------------------------------------------------


class TestSshRun:
    """Verify ssh_run delegates to subprocess and handles errors."""

    def test_success_returns_completed_process(self) -> None:
        mock_result = subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout="proxmox01\n", stderr="")
        with patch("proxmox_srvbackup.adapters.ssh.commands.subprocess.run", return_value=mock_result) as mock_run:
            result = ssh_run("px01.example.com", "hostname", ssh_key="/root/.ssh/key", user="root", timeout=15)

        assert result.stdout == "proxmox01\n"
        assert result.returncode == 0
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "ssh"
        assert "/root/.ssh/key" in cmd
        assert "root@px01.example.com" in cmd
        assert cmd[-1] == "hostname"

    def test_nonzero_exit_raises_ssh_connection_error(self) -> None:
        mock_result = subprocess.CompletedProcess(args=["ssh"], returncode=255, stdout="", stderr="Connection refused")
        with (
            patch("proxmox_srvbackup.adapters.ssh.commands.subprocess.run", return_value=mock_result),
            pytest.raises(SSHConnectionError, match="exited with code 255"),
        ):
            ssh_run("host", "cmd", ssh_key="/key")

    def test_os_error_raises_ssh_connection_error(self) -> None:
        with (
            patch(
                "proxmox_srvbackup.adapters.ssh.commands.subprocess.run",
                side_effect=OSError("No such file or directory"),
            ),
            pytest.raises(SSHConnectionError, match="SSH to host failed"),
        ):
            ssh_run("host", "cmd", ssh_key="/key")

    def test_default_user_and_timeout(self) -> None:
        mock_result = subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout="", stderr="")
        with patch("proxmox_srvbackup.adapters.ssh.commands.subprocess.run", return_value=mock_result) as mock_run:
            ssh_run("host", "cmd", ssh_key="/key")

        cmd = mock_run.call_args[0][0]
        assert "root@host" in cmd
        assert "ConnectTimeout=15" in cmd


# ---------------------------------------------------------------------------
# ssh_pipe_to_file
# ---------------------------------------------------------------------------


class TestSshPipeToFile:
    """Verify ssh_pipe_to_file creates dirs, streams, and cleans up on failure."""

    def test_success_writes_to_file(self, tmp_path: Path) -> None:
        dest = tmp_path / "sub" / "dir" / "backup.tar.gz"
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (None, b"")
        mock_proc.returncode = 0

        with patch("proxmox_srvbackup.adapters.ssh.commands.subprocess.Popen", return_value=mock_proc):
            ssh_pipe_to_file("host", "tar czf -", dest, ssh_key="/key")

        assert dest.parent.exists()

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        dest = tmp_path / "a" / "b" / "c" / "file.gz"
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (None, b"")
        mock_proc.returncode = 0

        with patch("proxmox_srvbackup.adapters.ssh.commands.subprocess.Popen", return_value=mock_proc):
            ssh_pipe_to_file("host", "cmd", dest, ssh_key="/key")

        assert dest.parent.exists()

    def test_nonzero_exit_removes_file_and_raises(self, tmp_path: Path) -> None:
        dest = tmp_path / "backup.tar.gz"
        dest.write_bytes(b"partial data")
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (None, b"remote error")
        mock_proc.returncode = 1

        with (
            patch("proxmox_srvbackup.adapters.ssh.commands.subprocess.Popen", return_value=mock_proc),
            pytest.raises(SSHConnectionError, match="exited with code 1"),
        ):
            ssh_pipe_to_file("host", "cmd", dest, ssh_key="/key")

        assert not dest.exists()

    def test_os_error_raises_ssh_connection_error(self, tmp_path: Path) -> None:
        dest = tmp_path / "backup.tar.gz"
        with (
            patch(
                "proxmox_srvbackup.adapters.ssh.commands.subprocess.Popen",
                side_effect=OSError("command not found"),
            ),
            pytest.raises(SSHConnectionError, match="SSH pipe to host failed"),
        ):
            ssh_pipe_to_file("host", "cmd", dest, ssh_key="/key")

    def test_includes_stream_opts(self, tmp_path: Path) -> None:
        dest = tmp_path / "backup.tar.gz"
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (None, b"")
        mock_proc.returncode = 0

        with patch("proxmox_srvbackup.adapters.ssh.commands.subprocess.Popen", return_value=mock_proc) as mock_popen:
            ssh_pipe_to_file("host", "cmd", dest, ssh_key="/key")

        cmd = mock_popen.call_args[0][0]
        assert "ServerAliveInterval=60" in cmd
        assert "ServerAliveCountMax=3" in cmd


# ---------------------------------------------------------------------------
# local_run
# ---------------------------------------------------------------------------


class TestLocalRun:
    """Verify local_run executes shell commands and handles errors."""

    def test_success_returns_completed_process(self) -> None:
        mock_result = subprocess.CompletedProcess(args=["echo"], returncode=0, stdout="hello\n", stderr="")
        with patch("proxmox_srvbackup.adapters.ssh.commands.subprocess.run", return_value=mock_result) as mock_run:
            result = local_run("echo hello")

        assert result.stdout == "hello\n"
        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args
        assert call_kwargs.kwargs["shell"] is True

    def test_nonzero_exit_raises_ssh_connection_error(self) -> None:
        mock_result = subprocess.CompletedProcess(args=["false"], returncode=1, stdout="", stderr="command failed")
        with (
            patch("proxmox_srvbackup.adapters.ssh.commands.subprocess.run", return_value=mock_result),
            pytest.raises(SSHConnectionError, match="Local command exited with code 1"),
        ):
            local_run("false")

    def test_os_error_raises_ssh_connection_error(self) -> None:
        with (
            patch(
                "proxmox_srvbackup.adapters.ssh.commands.subprocess.run",
                side_effect=OSError("cannot execute"),
            ),
            pytest.raises(SSHConnectionError, match="Local command failed"),
        ):
            local_run("nonexistent-cmd")


# ---------------------------------------------------------------------------
# local_pipe_to_file
# ---------------------------------------------------------------------------


class TestLocalPipeToFile:
    """Verify local_pipe_to_file streams to file and handles errors."""

    def test_success_creates_parent_dirs(self, tmp_path: Path) -> None:
        dest = tmp_path / "sub" / "output.gz"
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (None, b"")
        mock_proc.returncode = 0

        with patch("proxmox_srvbackup.adapters.ssh.commands.subprocess.Popen", return_value=mock_proc):
            local_pipe_to_file("echo hello", dest)

        assert dest.parent.exists()

    def test_nonzero_exit_removes_file_and_raises(self, tmp_path: Path) -> None:
        dest = tmp_path / "output.gz"
        dest.write_bytes(b"partial")
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (None, b"pipe broke")
        mock_proc.returncode = 1

        with (
            patch("proxmox_srvbackup.adapters.ssh.commands.subprocess.Popen", return_value=mock_proc),
            pytest.raises(SSHConnectionError, match="Local pipe exited with code 1"),
        ):
            local_pipe_to_file("cmd", dest)

        assert not dest.exists()

    def test_os_error_raises_ssh_connection_error(self, tmp_path: Path) -> None:
        dest = tmp_path / "output.gz"
        with (
            patch(
                "proxmox_srvbackup.adapters.ssh.commands.subprocess.Popen",
                side_effect=OSError("no such command"),
            ),
            pytest.raises(SSHConnectionError, match="Local pipe failed"),
        ):
            local_pipe_to_file("cmd", dest)

    def test_shell_true_is_used(self, tmp_path: Path) -> None:
        dest = tmp_path / "output.gz"
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (None, b"")
        mock_proc.returncode = 0

        with patch("proxmox_srvbackup.adapters.ssh.commands.subprocess.Popen", return_value=mock_proc) as mock_popen:
            local_pipe_to_file("echo hello | gzip", dest)

        call_kwargs = mock_popen.call_args
        assert call_kwargs.kwargs["shell"] is True
