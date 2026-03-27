"""Module entry stories ensuring `python -m` mirrors the CLI."""

from __future__ import annotations

import os
import runpy
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import lib_cli_exit_tools
import pytest

from proxmox_srvbackup import __init__conf__, entry
from proxmox_srvbackup.adapters import cli as cli_mod

# Ensure subprocess can find the package even without editable install.
_SRC_DIR = str(Path(__file__).resolve().parents[1] / "src")


def _subprocess_env() -> dict[str, str]:
    """Build env dict with src/ on PYTHONPATH for subprocess tests."""
    existing = os.environ.get("PYTHONPATH", "")
    pythonpath = f"{_SRC_DIR}{os.pathsep}{existing}" if existing else _SRC_DIR
    return {**os.environ, "PYTHONPATH": pythonpath}


@pytest.mark.os_agnostic
def test_module_entry_executes_cli_and_shows_help(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """python -m invocation with no args shows help and exits 0."""
    monkeypatch.setattr(sys, "argv", ["proxmox_srvbackup"], raising=False)

    with pytest.raises(SystemExit) as exc:
        runpy.run_module("proxmox_srvbackup.__main__", run_name="__main__")

    captured = capsys.readouterr()
    assert exc.value.code == 0
    assert "Usage:" in captured.out
    assert __init__conf__.shell_command in captured.out


@pytest.mark.os_agnostic
def test_module_entry_formats_exceptions_via_exit_helpers(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    strip_ansi: Callable[[str], str],
) -> None:
    """Exceptions during module entry are formatted by lib_cli_exit_tools."""
    monkeypatch.setattr(sys, "argv", ["proxmox_srvbackup", "fail"], raising=False)
    monkeypatch.setattr(lib_cli_exit_tools.config, "traceback", False, raising=False)
    monkeypatch.setattr(lib_cli_exit_tools.config, "traceback_force_color", False, raising=False)

    with pytest.raises(SystemExit) as exc:
        runpy.run_module("proxmox_srvbackup.__main__", run_name="__main__")

    plain_err = strip_ansi(capsys.readouterr().err)
    assert exc.value.code != 0
    assert "RuntimeError" in plain_err or "I should fail" in plain_err


@pytest.mark.os_agnostic
def test_module_entry_traceback_flag_prints_full_traceback(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    strip_ansi: Callable[[str], str],
) -> None:
    """--traceback via module entry prints complete traceback on error."""
    monkeypatch.setattr(sys, "argv", ["proxmox_srvbackup", "--traceback", "fail"])
    monkeypatch.setattr(lib_cli_exit_tools.config, "traceback", False, raising=False)
    monkeypatch.setattr(lib_cli_exit_tools.config, "traceback_force_color", False, raising=False)

    with pytest.raises(SystemExit) as exc:
        runpy.run_module("proxmox_srvbackup.__main__", run_name="__main__")

    plain_err = strip_ansi(capsys.readouterr().err)

    assert exc.value.code != 0
    assert "Traceback (most recent call last)" in plain_err
    assert "RuntimeError: I should fail" in plain_err
    assert "[TRUNCATED" not in plain_err
    assert lib_cli_exit_tools.config.traceback is False
    assert lib_cli_exit_tools.config.traceback_force_color is False


@pytest.mark.os_agnostic
def test_module_entry_cli_exports_all_registered_commands() -> None:
    """CLI facade exports all registered commands."""
    expected_commands = {
        "cli_config",
        "cli_config_deploy",
        "cli_config_generate_examples",
        "cli_fail",
        "cli_hello",
        "cli_info",
        "cli_logdemo",
        "cli_send_email",
        "cli_send_notification",
    }
    exported = {name for name in dir(cli_mod) if name.startswith("cli_")}
    assert expected_commands.issubset(exported)


@pytest.mark.os_agnostic
def test_module_entry_subprocess_help() -> None:
    """Verify `python -m proxmox_srvbackup --help` works via subprocess.

    This tests the true CLI invocation path that end-users would experience,
    complementing the runpy-based tests that run in-process.
    """
    result = subprocess.run(
        [sys.executable, "-m", "proxmox_srvbackup", "--help"],
        capture_output=True,
        timeout=30,
        check=False,
        encoding="utf-8",
        errors="replace",
        env=_subprocess_env(),
    )
    assert result.returncode == 0
    assert "Usage:" in result.stdout
    assert __init__conf__.shell_command in result.stdout


@pytest.mark.os_agnostic
def test_module_entry_subprocess_version() -> None:
    """Verify `python -m proxmox_srvbackup --version` outputs version."""
    result = subprocess.run(
        [sys.executable, "-m", "proxmox_srvbackup", "--version"],
        capture_output=True,
        timeout=30,
        check=False,
        encoding="utf-8",
        errors="replace",
        env=_subprocess_env(),
    )
    assert result.returncode == 0
    assert __init__conf__.version in result.stdout


@pytest.mark.os_agnostic
def test_entry_main_invokes_cli_with_help(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """entry.main() wires production services and invokes CLI.

    This tests the console script entry point used by pip-installed commands
    (proxmox_srvbackup, proxmox-srvbackup).
    """
    monkeypatch.setattr(sys, "argv", ["proxmox_srvbackup", "--help"])

    exit_code = entry.main()

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Usage:" in captured.out
    assert __init__conf__.shell_command in captured.out


@pytest.mark.os_agnostic
def test_entry_main_returns_nonzero_on_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    strip_ansi: Callable[[str], str],
) -> None:
    """entry.main() returns non-zero exit code on CLI errors."""
    monkeypatch.setattr(sys, "argv", ["proxmox_srvbackup", "fail"])
    monkeypatch.setattr(lib_cli_exit_tools.config, "traceback", False)
    monkeypatch.setattr(lib_cli_exit_tools.config, "traceback_force_color", False)

    exit_code = entry.main()

    plain_err = strip_ansi(capsys.readouterr().err)
    assert exit_code != 0
    assert "RuntimeError" in plain_err or "I should fail" in plain_err
