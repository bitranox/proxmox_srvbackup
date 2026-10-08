"""An attachment btx_lib_mail refuses on security grounds exits 77, through the real ``main()``.

The refusal is btx_lib_mail's own check, run by the real ``send_email`` adapter: only the SMTP
transport is replaced, by a recorder, so a test proves both the exit code and that nothing was
delivered. ``AttachmentSecurityError`` is neither a ``ValueError`` nor a ``RuntimeError``, so
without its own branch it fell into the catch-all as exit 1, "Unexpected error".
"""

from __future__ import annotations

import dataclasses
import shutil
import tempfile
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any

import pytest
from btx_lib_mail import ConfMail
from lib_layered_config import Config

from proxmox_srvbackup.adapters.cli.exit_codes import ExitCode
from proxmox_srvbackup.adapters.cli.main import main
from proxmox_srvbackup.adapters.email.config import load_email_config_from_dict
from proxmox_srvbackup.adapters.email.transport import send_email
from proxmox_srvbackup.composition import AppServices, build_testing

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Sequence

    from btx_lib_mail.lib_mail import DeliveryOptions

    from proxmox_srvbackup.adapters.email.config import EmailConfig

EMAIL = {"email": {"smtp_hosts": ["smtp.test.com:587"], "from_address": "sender@test.com"}}
SEND_EMAIL = ["send-email", "--to", "recipient@test.com", "--subject", "s", "--body", "b"]
REFUSED = "Error: Attachment refused by security policy - "


class _Recording:
    """A transport that records each recipient it is handed and sends nothing."""

    def __init__(self) -> None:
        self.recipients: list[str] = []

    def deliver(self, *, host: str, sender: str, recipient: str, message: IO[bytes], delivery: DeliveryOptions) -> None:
        self.recipients.append(recipient)


def _real_send_email(transport: _Recording) -> Callable[..., bool]:
    """The production ``send_email`` adapter with only its SMTP transport replaced."""

    def send(
        *,
        config: EmailConfig,
        recipients: str | Sequence[str] | None = None,
        subject: str,
        body: str = "",
        body_html: str = "",
        from_address: str | None = None,
        attachments: Sequence[Path] | None = None,
    ) -> bool:
        return send_email(
            config=config,
            recipients=recipients,
            subject=subject,
            body=body,
            body_html=body_html,
            from_address=from_address,
            attachments=attachments,
            transport=transport,
        )

    return send


def _services(transport: _Recording, data: dict[str, Any]) -> Callable[[], AppServices]:
    """The testing composition with the production config loader and the real send adapter.

    The production loader, because the in-memory one does not read the ``[email.attachments]``
    section, so the warn-mode test would run with the strict default.
    """
    config = Config(data, {})

    def get_config(**_kwargs: Any) -> Config:
        return config

    def build() -> AppServices:
        return dataclasses.replace(
            build_testing(),
            get_config=get_config,
            load_email_config_from_dict=load_email_config_from_dict,
            send_email=_real_send_email(transport),
        )

    return build


def _send_with(attachment: Path, transport: _Recording, data: dict[str, Any] = EMAIL) -> int:
    return main([*SEND_EMAIL, "--attachment", str(attachment)], services_factory=_services(transport, data))


def _error_lines(err: str) -> list[str]:
    return [line for line in err.splitlines() if line.startswith("Error:")]


def _is_blocked(directory: Path) -> bool:
    resolved = directory.resolve()
    return any(resolved.is_relative_to(blocked.resolve()) for blocked in ConfMail().attachment_blocked_directories)


def _a_file_in_a_blocked_directory() -> Path:
    for directory in sorted(ConfMail().attachment_blocked_directories):
        if not directory.is_dir():
            continue
        for entry in sorted(directory.iterdir()):
            if entry.is_file() and not entry.is_symlink():
                return entry
    raise AssertionError("no regular file directly inside any default blocked directory on this OS")


@pytest.fixture
def unblocked_dir(tmp_path: Path) -> Iterator[Path]:
    """A fresh directory under no default blocked directory, so only the file itself is judged.

    pytest's tmp_path is under /var on macOS (/private/var/folders), which the defaults block.
    """
    base = next((base for base in (tmp_path, Path.home(), Path.cwd()) if not _is_blocked(base)), None)
    assert base is not None, "no candidate directory is outside the default blocked directories"
    directory = Path(tempfile.mkdtemp(prefix="attachment-refused-", dir=base))
    yield directory
    shutil.rmtree(directory, ignore_errors=True)


@pytest.mark.os_agnostic
def test_the_attachment_refused_code_is_sysexits_ex_noperm() -> None:
    assert ExitCode.ATTACHMENT_REFUSED == 77


@pytest.mark.os_agnostic
def test_a_blocked_extension_exits_77_with_one_error_line_and_delivers_nothing(
    capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture, unblocked_dir: Path
) -> None:
    attachment = unblocked_dir / "x.exe"
    attachment.write_bytes(b"MZ")
    transport = _Recording()

    exit_code = _send_with(attachment, transport)

    err = capsys.readouterr().err
    assert exit_code == 77
    assert _error_lines(err) == [f'{REFUSED}extension ".exe" is blocked: "{attachment.resolve()}"']
    assert "Unexpected error" not in err
    assert [record.getMessage() for record in caplog.records if record.exc_info] == []
    assert transport.recipients == []


@pytest.mark.os_agnostic
def test_a_file_in_a_blocked_directory_exits_77_with_one_error_line_and_delivers_nothing(
    capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    attachment = _a_file_in_a_blocked_directory()
    transport = _Recording()

    exit_code = _send_with(attachment, transport)

    err = capsys.readouterr().err
    lines = _error_lines(err)
    assert exit_code == 77
    assert len(lines) == 1
    assert lines[0].startswith(f"{REFUSED}path under blocked directory ")
    assert "Unexpected error" not in err
    assert [record.getMessage() for record in caplog.records if record.exc_info] == []
    assert transport.recipients == []


@pytest.mark.os_agnostic
def test_an_ordinary_attachment_is_delivered(capsys: pytest.CaptureFixture[str], unblocked_dir: Path) -> None:
    """The control: the same wiring delivers a harmless file, so the 77 above is the refusal."""
    attachment = unblocked_dir / "report.txt"
    attachment.write_text("ok", encoding="utf-8")
    transport = _Recording()

    exit_code = _send_with(attachment, transport)

    assert exit_code == 0, capsys.readouterr().err
    assert transport.recipients == ["recipient@test.com"]


@pytest.mark.os_agnostic
def test_with_security_violations_set_to_warn_the_blocked_file_is_skipped_and_the_message_sent(
    capsys: pytest.CaptureFixture[str], unblocked_dir: Path
) -> None:
    """77 belongs to the strict setting: in warn mode btx_lib_mail drops the file and sends the rest."""
    attachment = unblocked_dir / "x.exe"
    attachment.write_bytes(b"MZ")
    transport = _Recording()
    warn = {"email": {**EMAIL["email"], "attachments": {"raise_on_security_violation": False}}}

    exit_code = _send_with(attachment, transport, warn)

    assert exit_code == 0, capsys.readouterr().err
    assert transport.recipients == ["recipient@test.com"]
