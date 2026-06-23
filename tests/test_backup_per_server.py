"""Tests for per-server backup type control (backup_configfiles / backup_snapshot).

Verifies that:
- Per-server booleans are parsed from TOML config (native bool).
- Per-server booleans are parsed from .env overrides (string "true"/"false").
- The _as_bool helper coerces strings and bools correctly.
- Disabled backup types are skipped in the orchestrator.
- Skipped types do not count as errors in BackupResult/BackupSummary.
- Dry-run output reflects which types are enabled per server.
"""

from __future__ import annotations

import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from click.testing import CliRunner

from proxmox_srvbackup.adapters.cli.commands.backup import (
    _as_bool,  # pyright: ignore[reportPrivateUsage]
    _servers_from_config,  # pyright: ignore[reportPrivateUsage]
)
from proxmox_srvbackup.adapters.cli.root import cli
from proxmox_srvbackup.domain.models import BackupResult, BackupSummary

# ---------------------------------------------------------------------------
# _as_bool helper
# ---------------------------------------------------------------------------


class TestAsBool:
    """Verify _as_bool coerces TOML bools and .env strings correctly."""

    def test_native_true(self) -> None:
        assert _as_bool(True, False) is True

    def test_native_false(self) -> None:
        assert _as_bool(False, True) is False

    def test_string_true(self) -> None:
        assert _as_bool("true", False) is True

    def test_string_false(self) -> None:
        assert _as_bool("false", True) is False

    def test_string_zero(self) -> None:
        assert _as_bool("0", True) is False

    def test_string_no(self) -> None:
        assert _as_bool("no", True) is False

    def test_string_off(self) -> None:
        assert _as_bool("off", True) is False

    def test_string_yes(self) -> None:
        assert _as_bool("yes", False) is True

    def test_string_one(self) -> None:
        assert _as_bool("1", False) is True

    def test_empty_string_is_falsy(self) -> None:
        assert _as_bool("", True) is False

    def test_string_false_case_insensitive(self) -> None:
        assert _as_bool("FALSE", True) is False
        assert _as_bool("False", True) is False

    def test_string_with_whitespace(self) -> None:
        assert _as_bool("  false  ", True) is False
        assert _as_bool("  true  ", False) is True

    def test_non_bool_non_string_returns_default(self) -> None:
        assert _as_bool(None, True) is True
        assert _as_bool(None, False) is False
        assert _as_bool(42, True) is True


# ---------------------------------------------------------------------------
# _servers_from_config parsing
# ---------------------------------------------------------------------------


class TestServersFromConfig:
    """Verify _servers_from_config reads per-server backup flags."""

    def test_defaults_both_true(self) -> None:
        config = {
            "backup": {
                "servers": {
                    "px01": {"hostname": "px01.example.com"},
                },
            },
        }
        servers = _servers_from_config(config)
        assert len(servers) == 1
        assert servers[0].backup_configfiles is True
        assert servers[0].backup_snapshot is True

    def test_toml_native_bools(self) -> None:
        config = {
            "backup": {
                "servers": {
                    "fw": {
                        "hostname": "fw.example.com",
                        "backup_configfiles": True,
                        "backup_snapshot": False,
                    },
                },
            },
        }
        servers = _servers_from_config(config)
        assert servers[0].backup_configfiles is True
        assert servers[0].backup_snapshot is False

    def test_env_string_bools(self) -> None:
        """Simulate values as they arrive from .env (strings, not bools)."""
        config = {
            "backup": {
                "servers": {
                    "fw": {
                        "hostname": "fw.example.com",
                        "backup_configfiles": "true",
                        "backup_snapshot": "false",
                    },
                },
            },
        }
        servers = _servers_from_config(config)
        assert servers[0].backup_configfiles is True
        assert servers[0].backup_snapshot is False

    def test_is_local_string_from_env(self) -> None:
        """is_local also gets coerced from .env strings."""
        config = {
            "backup": {
                "servers": {
                    "pbs": {
                        "hostname": "pbs.example.com",
                        "is_local": "true",
                    },
                },
            },
        }
        servers = _servers_from_config(config)
        assert servers[0].is_local is True

    def test_is_local_string_false_from_env(self) -> None:
        config = {
            "backup": {
                "servers": {
                    "px01": {
                        "hostname": "px01.example.com",
                        "is_local": "false",
                    },
                },
            },
        }
        servers = _servers_from_config(config)
        assert servers[0].is_local is False


# ---------------------------------------------------------------------------
# BackupResult.has_errors with skipped types
# ---------------------------------------------------------------------------


class TestBackupResultSkipped:
    """Verify has_errors ignores skipped backup types."""

    def test_skipped_zfs_not_an_error(self) -> None:
        r = BackupResult(server="fw", config_ok=True, zfs_skipped=True)
        assert r.has_errors is False

    def test_skipped_config_not_an_error(self) -> None:
        r = BackupResult(server="x", config_skipped=True, zfs_ok=True)
        assert r.has_errors is False

    def test_both_skipped_not_an_error(self) -> None:
        r = BackupResult(server="x", config_skipped=True, zfs_skipped=True)
        assert r.has_errors is False

    def test_failed_config_still_error_when_not_skipped(self) -> None:
        r = BackupResult(server="x", config_ok=False, config_error="fail", zfs_ok=True)
        assert r.has_errors is True

    def test_failed_zfs_still_error_when_not_skipped(self) -> None:
        r = BackupResult(server="x", config_ok=True, zfs_ok=False, zfs_error="fail")
        assert r.has_errors is True

    def test_summary_all_ok_with_skipped(self) -> None:
        s = BackupSummary(
            results=(
                BackupResult(server="px01", config_ok=True, zfs_ok=True),
                BackupResult(server="fw", config_ok=True, zfs_skipped=True),
            ),
        )
        assert s.all_ok is True
        assert len(s.failed_servers) == 0


# ---------------------------------------------------------------------------
# End-to-end: .env overrides per-server settings through real config loader
# ---------------------------------------------------------------------------


class TestDotenvPerServerOverride:
    """Verify per-server booleans flow through .env -> config -> parser."""

    def test_env_override_disables_snapshot(self, clear_config_cache: None) -> None:
        """A .env file with BACKUP__SERVERS__<NAME>__BACKUP_SNAPSHOT=false
        should produce a ServerConfig with backup_snapshot=False."""
        from proxmox_srvbackup.adapters.config.loader import get_config

        env_content = "BACKUP__SERVERS__PROXMOX01__BACKUP_SNAPSHOT=false\n"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write(env_content)
            env_path = f.name

        try:
            get_config.cache_clear()
            config = get_config(dotenv_path=env_path)
            servers = _servers_from_config(config.as_dict())

            px01 = next(s for s in servers if s.name == "proxmox01")
            assert px01.backup_snapshot is False
            # configfiles should remain at default (true from TOML)
            assert px01.backup_configfiles is True
        finally:
            Path(env_path).unlink(missing_ok=True)
            get_config.cache_clear()

    def test_env_override_disables_configfiles(self, clear_config_cache: None) -> None:
        from proxmox_srvbackup.adapters.config.loader import get_config

        env_content = "BACKUP__SERVERS__PROXMOX02__BACKUP_CONFIGFILES=false\n"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write(env_content)
            env_path = f.name

        try:
            get_config.cache_clear()
            config = get_config(dotenv_path=env_path)
            servers = _servers_from_config(config.as_dict())

            px02 = next(s for s in servers if s.name == "proxmox02")
            assert px02.backup_configfiles is False
            assert px02.backup_snapshot is True
        finally:
            Path(env_path).unlink(missing_ok=True)
            get_config.cache_clear()


# ---------------------------------------------------------------------------
# CLI dry-run reflects per-server backup types
# ---------------------------------------------------------------------------


class TestDryRunOutput:
    """Verify dry-run output shows which types are enabled per server."""

    def test_dry_run_shows_config_only(
        self,
        cli_runner: CliRunner,
        config_cli_context: Callable[[dict[str, Any]], Callable[..., Any]],
    ) -> None:
        factory = config_cli_context(
            {
                "backup": {
                    "servers": {
                        "fw": {
                            "hostname": "fw.example.com",
                            "backup_configfiles": True,
                            "backup_snapshot": False,
                        },
                    },
                },
            }
        )
        result = cli_runner.invoke(cli, ["backup", "--dry-run"], obj=factory)
        assert result.exit_code == 0
        assert "[config]" in result.output
        assert "[config+zfs]" not in result.output

    def test_dry_run_shows_both_types(
        self,
        cli_runner: CliRunner,
        config_cli_context: Callable[[dict[str, Any]], Callable[..., Any]],
    ) -> None:
        factory = config_cli_context(
            {
                "backup": {
                    "servers": {
                        "px01": {
                            "hostname": "px01.example.com",
                            "backup_configfiles": True,
                            "backup_snapshot": True,
                        },
                    },
                },
            }
        )
        result = cli_runner.invoke(cli, ["backup", "--dry-run"], obj=factory)
        assert result.exit_code == 0
        assert "[config+zfs]" in result.output

    def test_dry_run_shows_zfs_only(
        self,
        cli_runner: CliRunner,
        config_cli_context: Callable[[dict[str, Any]], Callable[..., Any]],
    ) -> None:
        factory = config_cli_context(
            {
                "backup": {
                    "servers": {
                        "px01": {
                            "hostname": "px01.example.com",
                            "backup_configfiles": False,
                            "backup_snapshot": True,
                        },
                    },
                },
            }
        )
        result = cli_runner.invoke(cli, ["backup", "--dry-run"], obj=factory)
        assert result.exit_code == 0
        assert "[zfs]" in result.output
        assert "[config+zfs]" not in result.output

    def test_dry_run_shows_none_when_both_disabled(
        self,
        cli_runner: CliRunner,
        config_cli_context: Callable[[dict[str, Any]], Callable[..., Any]],
    ) -> None:
        factory = config_cli_context(
            {
                "backup": {
                    "servers": {
                        "px01": {
                            "hostname": "px01.example.com",
                            "backup_configfiles": False,
                            "backup_snapshot": False,
                        },
                    },
                },
            }
        )
        result = cli_runner.invoke(cli, ["backup", "--dry-run"], obj=factory)
        assert result.exit_code == 0
        assert "[none]" in result.output
