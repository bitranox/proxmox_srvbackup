"""Exit codes and stderr through the real ``main()`` entry point.

``CliRunner.invoke(cli, ...)`` calls the click command tree directly and never runs
``main()``'s ``standalone_mode=False`` handling, which is where a bare ``SystemExit`` from a
command falls into the catch-all branch and is printed to stderr as ``SystemExit: N`` - text
a user reads as a crash. These tests go through ``main()`` itself, as a console script does,
with the services replaced at the composition seam.
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Any

import click
import pytest
from lib_layered_config import Config

from proxmox_srvbackup.adapters.cli.main import main
from proxmox_srvbackup.adapters.memory.email import EmailSpy
from proxmox_srvbackup.composition import AppServices, build_testing
from proxmox_srvbackup.domain.models import BackupResult, BackupSummary

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

EMAIL = {"email": {"smtp_hosts": ["smtp.test.com:587"], "from_address": "sender@test.com"}}
SEND_EMAIL = ["send-email", "--to", "recipient@test.com", "--subject", "Test", "--body", "Hello"]
SEND_NOTIFICATION = ["send-notification", "--to", "admin@test.com", "--subject", "Alert", "--message", "m"]
ONE_SERVER = {"backup": {"servers": {"node1": {"hostname": "node1.test"}}, "bootstrap_key": "/keys/bootstrap"}}


def _services(data: dict[str, Any], **overrides: Any) -> Callable[[], AppServices]:
    config = Config(data, {})

    def get_config(**_kwargs: Any) -> Config:
        return config

    def build() -> AppServices:
        return dataclasses.replace(build_testing(), get_config=get_config, **overrides)

    return build


def _failing_spy() -> EmailSpy:
    spy = EmailSpy()
    spy.should_fail = True
    return spy


def _raising(error: Exception) -> Callable[..., Any]:
    def raise_it(*_args: Any, **_kwargs: Any) -> Any:
        raise error

    return raise_it


@pytest.mark.os_agnostic
def test_send_email_without_smtp_hosts_exits_78_without_printing_systemexit(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main(SEND_EMAIL, services_factory=_services({}))

    err = capsys.readouterr().err
    assert exit_code == 78
    assert "No SMTP hosts configured" in err
    assert "SystemExit" not in err


@pytest.mark.os_agnostic
@pytest.mark.parametrize("args", [SEND_EMAIL, SEND_NOTIFICATION], ids=["send-email", "send-notification"])
def test_a_failed_send_exits_69_and_reports_it_once(capsys: pytest.CaptureFixture[str], args: list[str]) -> None:
    """click's Exit is a RuntimeError; the delivery handler must not re-handle it as a second failure."""
    spy = _failing_spy()
    exit_code = main(
        args,
        services_factory=_services(EMAIL, send_email=spy.send_email, send_notification=spy.send_notification),
    )

    err = capsys.readouterr().err
    assert exit_code == 69
    assert "sending failed" in err
    assert "SMTP delivery failed" not in err
    assert "Failed to send email" not in err
    assert "SystemExit" not in err


@pytest.mark.os_agnostic
def test_a_delivery_error_exits_69_without_printing_systemexit(capsys: pytest.CaptureFixture[str]) -> None:
    spy = EmailSpy()
    spy.raise_exception = RuntimeError("connection refused")
    exit_code = main(SEND_EMAIL, services_factory=_services(EMAIL, send_email=spy.send_email))

    err = capsys.readouterr().err
    assert exit_code == 69
    assert "connection refused" in err
    assert "SystemExit" not in err


@pytest.mark.os_agnostic
def test_a_config_display_error_exits_22_without_printing_systemexit(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["config"], services_factory=_services({}, display_config=_raising(ValueError("boom"))))

    err = capsys.readouterr().err
    assert exit_code == 22
    assert "boom" in err
    assert "SystemExit" not in err


@pytest.mark.os_agnostic
@pytest.mark.parametrize(
    ("error", "expected"),
    [(PermissionError("denied"), 13), (OSError("disk full"), 1)],
    ids=["permission-denied", "general-error"],
)
def test_a_deploy_failure_exits_with_its_code_without_printing_systemexit(
    capsys: pytest.CaptureFixture[str], error: Exception, expected: int
) -> None:
    services = _services({}, deploy_configuration=_raising(error))
    exit_code = main(["config-deploy", "--target", "user"], services_factory=services)

    err = capsys.readouterr().err
    assert exit_code == expected
    assert str(error) in err
    assert "SystemExit" not in err


@pytest.mark.os_agnostic
def test_a_deliberate_exit_inside_deploy_keeps_its_own_code(capsys: pytest.CaptureFixture[str]) -> None:
    """click's Exit is a RuntimeError; the deploy failure branch must let it through unrelabelled."""
    services = _services({}, deploy_configuration=_raising(click.exceptions.Exit(78)))
    exit_code = main(["config-deploy", "--target", "user"], services_factory=services)

    err = capsys.readouterr().err
    assert exit_code == 78
    assert "Failed to deploy configuration" not in err


@pytest.mark.os_agnostic
def test_a_generate_examples_failure_exits_1_without_printing_systemexit(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    blocker = tmp_path / "a-file"
    blocker.write_text("not a directory", encoding="utf-8")

    exit_code = main(
        ["config-generate-examples", "--destination", str(blocker / "sub")], services_factory=_services({})
    )

    err = capsys.readouterr().err
    assert exit_code == 1
    assert "Error:" in err
    assert "SystemExit" not in err


@pytest.mark.os_agnostic
def test_a_successful_command_exits_0(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["hello"], services_factory=_services({}))

    assert exit_code == 0
    assert "Hello World" in capsys.readouterr().out


@pytest.mark.os_agnostic
@pytest.mark.parametrize(
    ("args", "data", "expected", "message"),
    [
        (["backup"], {}, 1, "No servers configured"),
        (["backup", "--server", "absent"], ONE_SERVER, 22, "not found in configuration"),
        (["setup-keys"], {}, 1, "No bootstrap_key configured"),
    ],
    ids=["backup-no-servers", "backup-unknown-server", "setup-keys-no-bootstrap-key"],
)
def test_a_refused_backup_command_exits_with_its_code_without_printing_systemexit(
    capsys: pytest.CaptureFixture[str], args: list[str], data: dict[str, Any], expected: int, message: str
) -> None:
    exit_code = main(args, services_factory=_services(data))

    err = capsys.readouterr().err
    assert exit_code == expected
    assert message in err
    assert "SystemExit" not in err


def _failed_backup(*_args: Any, **_kwargs: Any) -> BackupSummary:
    return BackupSummary(results=(BackupResult(server="node1", config_ok=False, config_error="refused"),))


def _failed_key_setup(*_args: Any, **_kwargs: Any) -> dict[str, bool]:
    return {"node1": False}


@pytest.mark.os_agnostic
@pytest.mark.parametrize(
    ("args", "overrides"),
    [
        (["backup", "--dry-run"], {"backup_all": _failed_backup}),
        (["setup-keys"], {"setup_keys": _failed_key_setup}),
    ],
    ids=["backup-failed", "setup-keys-failed"],
)
def test_a_failed_backup_run_exits_1_without_printing_systemexit(
    capsys: pytest.CaptureFixture[str], args: list[str], overrides: dict[str, Any]
) -> None:
    exit_code = main(args, services_factory=_services(ONE_SERVER, **overrides))

    err = capsys.readouterr().err
    assert exit_code == 1
    assert "SystemExit" not in err
