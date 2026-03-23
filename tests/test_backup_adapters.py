"""Unit tests for backup adapter pure-logic functions.

Tests the deterministic, I/O-free portions of:
- retention.py: apply_retention with temp directories
- config_backup.py: _build_tar_command string building
- ssh/commands.py: _build_ssh_cmd argument list building
- setup_keys.py: _key_path path building
- orchestrator.py: BackupSettings extraction, _resolve_ssh_key
"""

from __future__ import annotations

from pathlib import Path

import pytest

from proxmox_srvbackup.adapters.backup.config_backup import _build_tar_command  # pyright: ignore[reportPrivateUsage]
from proxmox_srvbackup.adapters.backup.orchestrator import (
    BackupSettings,
    _resolve_ssh_key,  # pyright: ignore[reportPrivateUsage]
)
from proxmox_srvbackup.adapters.backup.retention import apply_retention
from proxmox_srvbackup.adapters.backup.setup_keys import _key_path  # pyright: ignore[reportPrivateUsage]
from proxmox_srvbackup.adapters.ssh.commands import _build_ssh_cmd  # pyright: ignore[reportPrivateUsage]
from proxmox_srvbackup.domain.errors import RetentionError
from proxmox_srvbackup.domain.models import ServerConfig

# ---------------------------------------------------------------------------
# _build_tar_command
# ---------------------------------------------------------------------------


class TestBuildTarCommand:
    """Verify tar command string construction."""

    def test_basic_paths(self) -> None:
        result = _build_tar_command(["/etc/pve", "/etc/network"], [])
        assert "tar --hard-dereference --ignore-failed-read -czf -" in result
        assert "/etc/pve /etc/network" in result
        assert "--exclude" not in result

    def test_with_excludes(self) -> None:
        result = _build_tar_command(
            ["/etc/pve"],
            ["/etc/pve/secrets", "/tmp"],
        )
        assert "--exclude=/etc/pve/secrets" in result
        assert "--exclude=/tmp" in result
        assert "/etc/pve" in result

    def test_empty_paths(self) -> None:
        result = _build_tar_command([], [])
        assert "tar --hard-dereference --ignore-failed-read -czf -" in result

    def test_stderr_redirect(self) -> None:
        result = _build_tar_command(["/etc"], [])
        assert result.endswith("2>/dev/null")


# ---------------------------------------------------------------------------
# _build_ssh_cmd
# ---------------------------------------------------------------------------


class TestBuildSshCmd:
    """Verify SSH command argument list construction."""

    def test_basic_command(self) -> None:
        cmd = _build_ssh_cmd(
            "px01.example.com",
            "hostname",
            ssh_key="/root/.ssh/backup_pull_px01",
            user="root",
            timeout=15,
        )
        assert cmd[0] == "ssh"
        assert "-i" in cmd
        assert "/root/.ssh/backup_pull_px01" in cmd
        assert "ConnectTimeout=15" in cmd[cmd.index("-o") + 1]
        assert "root@px01.example.com" in cmd
        assert cmd[-1] == "hostname"

    def test_batch_mode_and_strict_host(self) -> None:
        cmd = _build_ssh_cmd(
            "host",
            "cmd",
            ssh_key="/key",
            user="root",
            timeout=10,
        )
        assert "BatchMode=yes" in cmd
        assert "StrictHostKeyChecking=accept-new" in cmd

    def test_extra_opts_included(self) -> None:
        cmd = _build_ssh_cmd(
            "host",
            "cmd",
            ssh_key="/key",
            user="root",
            timeout=10,
            extra_opts=["-o", "ServerAliveInterval=60"],
        )
        assert "ServerAliveInterval=60" in cmd

    def test_custom_user(self) -> None:
        cmd = _build_ssh_cmd(
            "host",
            "cmd",
            ssh_key="/key",
            user="backup",
            timeout=10,
        )
        assert "backup@host" in cmd


# ---------------------------------------------------------------------------
# _key_path
# ---------------------------------------------------------------------------


class TestKeyPath:
    """Verify SSH key path construction."""

    def test_standard_path(self) -> None:
        result = _key_path(Path("/root/.ssh"), "backup_pull", "proxmox01")
        assert result == Path("/root/.ssh/backup_pull_proxmox01")

    def test_custom_prefix(self) -> None:
        result = _key_path(Path("/opt/keys"), "myprefix", "server-name")
        assert result == Path("/opt/keys/myprefix_server-name")


# ---------------------------------------------------------------------------
# _resolve_ssh_key
# ---------------------------------------------------------------------------


class TestResolveSshKey:
    """Verify SSH key resolution from server config."""

    def test_builds_key_path(self) -> None:
        server = ServerConfig(name="px01", hostname="px01.example.com", zfs_pool="rpool")
        result = _resolve_ssh_key(server, "/root/.ssh", "backup_pull")
        assert result == "/root/.ssh/backup_pull_px01"


# ---------------------------------------------------------------------------
# BackupSettings dataclass
# ---------------------------------------------------------------------------


class TestBackupSettings:
    """Verify BackupSettings typed dataclass."""

    def test_defaults(self) -> None:
        s = BackupSettings(
            backup_base_dir=Path("/mnt/backups"),
            max_parallel=4,
            retention_count=3,
            ssh_user="root",
            ssh_connect_timeout=15,
            ssh_key_dir="/root/.ssh",
            ssh_key_prefix="backup_pull",
        )
        assert s.config_paths == []
        assert s.exclude_patterns == []
        assert s.bootstrap_key == ""

    def test_frozen(self) -> None:
        s = BackupSettings(
            backup_base_dir=Path("/mnt/backups"),
            max_parallel=4,
            retention_count=3,
            ssh_user="root",
            ssh_connect_timeout=15,
            ssh_key_dir="/root/.ssh",
            ssh_key_prefix="backup_pull",
        )
        with pytest.raises(AttributeError):
            s.max_parallel = 8  # type: ignore[misc]


# ---------------------------------------------------------------------------
# apply_retention
# ---------------------------------------------------------------------------


class TestApplyRetention:
    """Verify retention pruning with real temp directories."""

    def test_nonexistent_directory_returns_empty(self, tmp_path: Path) -> None:
        result = apply_retention(tmp_path / "does-not-exist", keep=3)
        assert result == []

    def test_fewer_files_than_keep_nothing_deleted(self, tmp_path: Path) -> None:
        for name in ["backup_2026-03-01.tar.gz", "backup_2026-03-02.tar.gz"]:
            (tmp_path / name).write_text("data")
        result = apply_retention(tmp_path, pattern="backup_*.tar.gz", keep=3)
        assert result == []
        assert len(list(tmp_path.iterdir())) == 2

    def test_exact_keep_count_nothing_deleted(self, tmp_path: Path) -> None:
        for name in ["backup_2026-03-01.tar.gz", "backup_2026-03-02.tar.gz", "backup_2026-03-03.tar.gz"]:
            (tmp_path / name).write_text("data")
        result = apply_retention(tmp_path, pattern="backup_*.tar.gz", keep=3)
        assert result == []

    def test_excess_files_oldest_deleted(self, tmp_path: Path) -> None:
        names = [
            "backup_2026-03-01.tar.gz",
            "backup_2026-03-02.tar.gz",
            "backup_2026-03-03.tar.gz",
            "backup_2026-03-04.tar.gz",
            "backup_2026-03-05.tar.gz",
        ]
        for name in names:
            (tmp_path / name).write_text("data")
        deleted = apply_retention(tmp_path, pattern="backup_*.tar.gz", keep=3)
        assert len(deleted) == 2
        deleted_names = [p.name for p in deleted]
        assert "backup_2026-03-01.tar.gz" in deleted_names
        assert "backup_2026-03-02.tar.gz" in deleted_names
        remaining = sorted(p.name for p in tmp_path.iterdir())
        assert remaining == [
            "backup_2026-03-03.tar.gz",
            "backup_2026-03-04.tar.gz",
            "backup_2026-03-05.tar.gz",
        ]

    def test_pattern_filters_unrelated_files(self, tmp_path: Path) -> None:
        (tmp_path / "backup_2026-03-01.tar.gz").write_text("data")
        (tmp_path / "backup_2026-03-02.tar.gz").write_text("data")
        (tmp_path / "backup_2026-03-03.tar.gz").write_text("data")
        (tmp_path / "backup_2026-03-04.tar.gz").write_text("data")
        (tmp_path / "unrelated.txt").write_text("keep me")
        deleted = apply_retention(tmp_path, pattern="backup_*.tar.gz", keep=2)
        assert len(deleted) == 2
        assert (tmp_path / "unrelated.txt").exists()

    def test_keep_one(self, tmp_path: Path) -> None:
        for i in range(5):
            (tmp_path / f"snap_{i:03d}.zfs.gz").write_text("data")
        deleted = apply_retention(tmp_path, pattern="snap_*.zfs.gz", keep=1)
        assert len(deleted) == 4
        remaining = list(tmp_path.iterdir())
        assert len(remaining) == 1
        assert remaining[0].name == "snap_004.zfs.gz"

    def test_permission_error_raises_retention_error(self, tmp_path: Path) -> None:
        for name in ["a.txt", "b.txt", "c.txt"]:
            (tmp_path / name).write_text("data")
        (tmp_path / "a.txt").chmod(0o000)
        tmp_path.chmod(0o555)
        try:
            with pytest.raises(RetentionError, match="Cannot delete"):
                apply_retention(tmp_path, pattern="*.txt", keep=1)
        finally:
            tmp_path.chmod(0o755)
            (tmp_path / "a.txt").chmod(0o644)

    def test_directories_ignored(self, tmp_path: Path) -> None:
        (tmp_path / "subdir").mkdir()
        (tmp_path / "file_01.txt").write_text("data")
        (tmp_path / "file_02.txt").write_text("data")
        deleted = apply_retention(tmp_path, pattern="*", keep=1)
        assert len(deleted) == 1
        assert (tmp_path / "subdir").is_dir()
