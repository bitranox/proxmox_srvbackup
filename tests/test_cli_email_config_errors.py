"""An email configuration the model refuses: one ``Error:`` line per problem, never a dump.

An invalid ``[email]`` section is a configuration error (exit 78) like any other, reported
the way the permission settings are: ``Error: Invalid configuration: email.<key>: <reason>``,
one line per problem. An invalid value given on the command line (``--timeout -5``) is an
invalid argument (exit 22) in the same form. Neither prints pydantic's multi-line report
with its documentation URL, which used to escape through ``main()``'s catch-all as exit 22.
"""

from __future__ import annotations

import dataclasses
import os
import subprocess
import sys
from typing import TYPE_CHECKING, Any

import pytest
from lib_layered_config import Config

from proxmox_srvbackup import __init__conf__
from proxmox_srvbackup.adapters.cli.main import main
from proxmox_srvbackup.adapters.email.config import load_email_config_from_dict
from proxmox_srvbackup.composition import AppServices, build_testing

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

VALID = {"smtp_hosts": ["smtp.example.com:587"], "from_address": "sender@example.com"}
SEND_EMAIL = ["send-email", "--to", "recipient@example.com", "--subject", "s", "--body", "b"]
SEND_NOTIFICATION = ["send-notification", "--to", "recipient@example.com", "--subject", "s", "--message", "m"]


def _services(email: object) -> Callable[[], AppServices]:
    """The testing composition over an ``[email]`` section, read by the production loader."""
    config = Config({"email": email}, {})

    def get_config(**_kwargs: Any) -> Config:
        return config

    return lambda: dataclasses.replace(
        build_testing(), get_config=get_config, load_email_config_from_dict=load_email_config_from_dict
    )


def _error_lines(err: str) -> list[str]:
    return [line for line in err.splitlines() if line.startswith("Error:")]


@pytest.mark.os_agnostic
@pytest.mark.parametrize("command", [SEND_EMAIL, SEND_NOTIFICATION], ids=["send-email", "send-notification"])
def test_an_invalid_email_section_exits_78_with_one_line_per_problem(
    capsys: pytest.CaptureFixture[str], command: list[str]
) -> None:
    exit_code = main(command, services_factory=_services({**VALID, "timeout": "soon", "use_starttls": "maybe"}))

    err = capsys.readouterr().err
    assert exit_code == 78, err
    keys = [line.split(": ")[2] for line in _error_lines(err)]
    assert sorted(keys) == ["email.timeout", "email.use_starttls"], err
    assert all(line.startswith("Error: Invalid configuration: ") for line in _error_lines(err))
    assert "errors.pydantic.dev" not in err
    assert "validation error" not in err


@pytest.mark.os_agnostic
def test_a_refused_value_names_its_file_key(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(SEND_EMAIL, services_factory=_services({**VALID, "timeout": -5}))

    err = capsys.readouterr().err
    assert exit_code == 78, err
    assert _error_lines(err) == ["Error: Invalid configuration: email.timeout: timeout must be positive, got -5.0"]


@pytest.mark.os_agnostic
@pytest.mark.parametrize("command", [SEND_EMAIL, SEND_NOTIFICATION], ids=["send-email", "send-notification"])
def test_an_unknown_email_key_exits_78_naming_it(capsys: pytest.CaptureFixture[str], command: list[str]) -> None:
    exit_code = main(command, services_factory=_services({**VALID, "smtp_host": "smtp.example.com"}))

    err = capsys.readouterr().err
    assert exit_code == 78, err
    assert _error_lines(err) == ["Error: Invalid configuration: email.smtp_host: unknown key"]


@pytest.mark.os_agnostic
def test_an_attachment_setting_is_named_by_its_configuration_key(capsys: pytest.CaptureFixture[str]) -> None:
    """The model flattens [email.attachments] to attachment_*; the user wrote the nested key."""
    email = {**VALID, "attachments": {"max_size_bytes": "large"}}
    exit_code = main(SEND_EMAIL, services_factory=_services(email))

    err = capsys.readouterr().err
    assert exit_code == 78, err
    lines = _error_lines(err)
    assert len(lines) == 1, err
    assert lines[0].startswith("Error: Invalid configuration: email.attachments.max_size_bytes: ")


@pytest.mark.os_agnostic
def test_an_email_section_that_is_not_a_table_exits_78(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(SEND_EMAIL, services_factory=_services("smtp.example.com"))

    err = capsys.readouterr().err
    assert exit_code == 78, err
    assert len(_error_lines(err)) == 1, err


@pytest.mark.os_agnostic
def test_an_invalid_option_value_exits_22_with_one_line(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main([*SEND_EMAIL, "--timeout", "-5"], services_factory=_services(VALID))

    err = capsys.readouterr().err
    assert exit_code == 22, err
    assert _error_lines(err) == ["Error: Invalid option value: email.timeout: timeout must be positive, got -5.0"]
    assert "errors.pydantic.dev" not in err


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="XDG_CONFIG_HOME locates the user layer on Linux")
def test_a_real_invalid_email_section_exits_78_before_sending(tmp_path: Path) -> None:
    """End to end through the real loader; the refusal comes before any connection is tried."""
    config_dir = tmp_path / __init__conf__.LAYEREDCONF_SLUG
    config_dir.mkdir()
    (config_dir / "config.toml").write_text(
        '[email]\nsmtp_hosts = ["smtp.invalid:587"]\ntimeout = -5\n', encoding="utf-8"
    )
    completed = subprocess.run(
        [sys.executable, "-m", "proxmox_srvbackup", "send-email", "--to", "a@example.com", "--subject", "s"],
        capture_output=True,
        check=False,
        env={**os.environ, "XDG_CONFIG_HOME": str(tmp_path)},
    )

    stderr = completed.stderr.decode("utf-8", "replace")
    assert completed.returncode == 78, stderr
    assert "Error: Invalid configuration: email.timeout: timeout must be positive, got -5.0" in stderr
    assert "Traceback" not in stderr
