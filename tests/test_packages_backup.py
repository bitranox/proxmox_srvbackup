"""Tests for package list backup adapter.

Verifies:
- Package list files are created with correct names and content.
- Both dpkg --get-selections and dpkg -l outputs are saved.
- Retention is applied per file type.
- Dry-run logs without executing.
- Local (is_local=True) and remote paths are dispatched correctly.
- build_packages_filename produces correct filenames.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from proxmox_srvbackup.adapters.backup.packages_backup import (
    _DPKG_LIST_CMD,  # pyright: ignore[reportPrivateUsage]
    _DPKG_SELECTIONS_CMD,  # pyright: ignore[reportPrivateUsage]
    backup_packages,
)
from proxmox_srvbackup.domain.behaviors import build_packages_filename
from proxmox_srvbackup.domain.models import ServerConfig

_FAKE_SELECTIONS = "vim\tinstall\ncurl\tinstall\n"
_FAKE_DPKG_LIST = "ii  vim  9.0  amd64  Vi IMproved\nii  curl  7.88  amd64  command line tool\n"


def _make_server(*, is_local: bool = False) -> ServerConfig:
    return ServerConfig(name="px01", hostname="px01.example.com", zfs_pool="rpool", is_local=is_local)


def _fake_ssh_run(host: str, command: str, **_kwargs: object) -> subprocess.CompletedProcess[str]:
    """Return fake dpkg output based on the command."""
    if command == _DPKG_SELECTIONS_CMD:
        return subprocess.CompletedProcess(args=command, returncode=0, stdout=_FAKE_SELECTIONS, stderr="")
    if command == _DPKG_LIST_CMD:
        return subprocess.CompletedProcess(args=command, returncode=0, stdout=_FAKE_DPKG_LIST, stderr="")
    return subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")


def _fake_local_run(command: str) -> subprocess.CompletedProcess[str]:
    """Return fake dpkg output for local commands."""
    if command == _DPKG_SELECTIONS_CMD:
        return subprocess.CompletedProcess(args=command, returncode=0, stdout=_FAKE_SELECTIONS, stderr="")
    if command == _DPKG_LIST_CMD:
        return subprocess.CompletedProcess(args=command, returncode=0, stdout=_FAKE_DPKG_LIST, stderr="")
    return subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")


class TestBuildPackagesFilename:
    """Verify package list filename construction."""

    def test_selections_filename(self) -> None:
        result = build_packages_filename("px01", "2026-03-27_14-30-00", "selections")
        assert result == "packages_selections_px01_2026-03-27_14-30-00.txt"

    def test_list_filename(self) -> None:
        result = build_packages_filename("px01", "2026-03-27_14-30-00", "list")
        assert result == "packages_list_px01_2026-03-27_14-30-00.txt"


class TestBackupPackagesRemote:
    """Verify remote package list backup via SSH."""

    @patch("proxmox_srvbackup.adapters.backup.packages_backup.ssh_run", side_effect=_fake_ssh_run)
    def test_creates_both_files(self, mock_ssh: MagicMock, tmp_path: Path) -> None:
        server = _make_server()
        backup_packages(server, backup_dir=tmp_path, ssh_key="/root/.ssh/key", retention_count=3)

        configs_dir = tmp_path / "px01" / "configs"
        selections_files = list(configs_dir.glob("packages_selections_*.txt"))
        list_files = list(configs_dir.glob("packages_list_*.txt"))
        assert len(selections_files) == 1
        assert len(list_files) == 1

    @patch("proxmox_srvbackup.adapters.backup.packages_backup.ssh_run", side_effect=_fake_ssh_run)
    def test_selections_content(self, mock_ssh: MagicMock, tmp_path: Path) -> None:
        server = _make_server()
        backup_packages(server, backup_dir=tmp_path, ssh_key="/root/.ssh/key")

        configs_dir = tmp_path / "px01" / "configs"
        selections_file = next(configs_dir.glob("packages_selections_*.txt"))
        content = selections_file.read_text(encoding="utf-8")
        assert "vim\tinstall" in content
        assert "curl\tinstall" in content

    @patch("proxmox_srvbackup.adapters.backup.packages_backup.ssh_run", side_effect=_fake_ssh_run)
    def test_list_content(self, mock_ssh: MagicMock, tmp_path: Path) -> None:
        server = _make_server()
        backup_packages(server, backup_dir=tmp_path, ssh_key="/root/.ssh/key")

        configs_dir = tmp_path / "px01" / "configs"
        list_file = next(configs_dir.glob("packages_list_*.txt"))
        content = list_file.read_text(encoding="utf-8")
        assert "vim" in content
        assert "curl" in content

    @patch("proxmox_srvbackup.adapters.backup.packages_backup.ssh_run", side_effect=_fake_ssh_run)
    def test_ssh_run_called_with_both_commands(self, mock_ssh: MagicMock, tmp_path: Path) -> None:
        server = _make_server()
        backup_packages(server, backup_dir=tmp_path, ssh_key="/root/.ssh/key")

        commands = [call.args[1] for call in mock_ssh.call_args_list]
        assert _DPKG_SELECTIONS_CMD in commands
        assert _DPKG_LIST_CMD in commands


class TestBackupPackagesLocal:
    """Verify local package list backup dispatches to local_run."""

    @patch("proxmox_srvbackup.adapters.backup.packages_backup.local_run", side_effect=_fake_local_run)
    def test_local_creates_both_files(self, mock_local: MagicMock, tmp_path: Path) -> None:
        server = _make_server(is_local=True)
        backup_packages(server, backup_dir=tmp_path, ssh_key="/root/.ssh/key")

        configs_dir = tmp_path / "px01" / "configs"
        assert len(list(configs_dir.glob("packages_selections_*.txt"))) == 1
        assert len(list(configs_dir.glob("packages_list_*.txt"))) == 1

    @patch("proxmox_srvbackup.adapters.backup.packages_backup.local_run", side_effect=_fake_local_run)
    def test_local_run_called_not_ssh(self, mock_local: MagicMock, tmp_path: Path) -> None:
        server = _make_server(is_local=True)
        with patch("proxmox_srvbackup.adapters.backup.packages_backup.ssh_run") as mock_ssh:
            backup_packages(server, backup_dir=tmp_path, ssh_key="/root/.ssh/key")
            mock_ssh.assert_not_called()
        assert mock_local.call_count == 2


class TestBackupPackagesDryRun:
    """Verify dry-run does not create files."""

    def test_dry_run_creates_no_files(self, tmp_path: Path) -> None:
        server = _make_server()
        backup_packages(server, backup_dir=tmp_path, ssh_key="/root/.ssh/key", dry_run=True)

        configs_dir = tmp_path / "px01" / "configs"
        assert not configs_dir.exists() or len(list(configs_dir.iterdir())) == 0


class TestBackupPackagesRetention:
    """Verify retention is applied to package list files."""

    @patch("proxmox_srvbackup.adapters.backup.packages_backup.ssh_run", side_effect=_fake_ssh_run)
    def test_retention_keeps_only_n_files(self, mock_ssh: MagicMock, tmp_path: Path) -> None:
        server = _make_server()
        configs_dir = tmp_path / "px01" / "configs"
        configs_dir.mkdir(parents=True)

        for i in range(5):
            (configs_dir / f"packages_selections_px01_2026-03-{20 + i:02d}_00-00-00.txt").write_text("old")
            (configs_dir / f"packages_list_px01_2026-03-{20 + i:02d}_00-00-00.txt").write_text("old")

        backup_packages(server, backup_dir=tmp_path, ssh_key="/root/.ssh/key", retention_count=3)

        selections_files = sorted(configs_dir.glob("packages_selections_*.txt"))
        list_files = sorted(configs_dir.glob("packages_list_*.txt"))
        assert len(selections_files) == 3
        assert len(list_files) == 3
