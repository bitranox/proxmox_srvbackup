"""What btx_lib_mail 4 refuses on this tool's behalf, pinned through this tool's own send path.

The send path hands every setting to btx_lib_mail and relies on it for four refusals this
tool does not repeat: more recipients or attachments than one send may carry, a Windows
executable attached on a POSIX host (and a POSIX script on Windows), and an SMTP port that is
not plain digits. Each test drives the tool's ``send_email`` or ``EmailConfig`` with the
library's defaults, so a btx_lib_mail release that stops refusing fails here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from btx_lib_mail.lib_mail import AttachmentSecurityError
from pydantic import ValidationError
from test_mail import RecordingTransport

from proxmox_srvbackup.adapters.email.config import describe_validation_error
from proxmox_srvbackup.adapters.email.sender import EmailConfig, send_email

if TYPE_CHECKING:
    from pathlib import Path

VALID = EmailConfig(smtp_hosts=["smtp.test.com:587"], from_address="app@example.com")

#: The library's own per-send limits (ConfMail.recipient_max_count, attachment_max_count).
LIBRARY_RECIPIENT_LIMIT = 1000
LIBRARY_ATTACHMENT_LIMIT = 100


@pytest.mark.os_agnostic
def test_more_recipients_than_the_library_allows_are_refused_before_any_delivery() -> None:
    """One recipient past the library's default limit refuses the whole send, no host is tried."""
    recipients = [f"r{n}@example.com" for n in range(LIBRARY_RECIPIENT_LIMIT + 1)]
    transport = RecordingTransport()

    with pytest.raises(ValueError, match=r"1001 recipients, more than recipient_max_count \(1000\)"):
        send_email(config=VALID, recipients=recipients, subject="s", transport=transport)

    assert transport.attempted_hosts == []


@pytest.mark.os_agnostic
def test_more_attachments_than_the_library_allows_are_refused_before_any_delivery(tmp_path: Path) -> None:
    """One attachment past the library's default limit refuses the whole send, no host is tried."""
    attachments: list[Path] = []
    for n in range(LIBRARY_ATTACHMENT_LIMIT + 1):
        path = tmp_path / f"a{n}.txt"
        path.write_text("a", encoding="utf-8")
        attachments.append(path)
    transport = RecordingTransport()

    with pytest.raises(ValueError, match=r"101 attachments, more than attachment_max_count \(100\)"):
        send_email(
            config=VALID, recipients="ops@example.com", subject="s", attachments=attachments, transport=transport
        )

    assert transport.attempted_hosts == []


@pytest.mark.os_agnostic
@pytest.mark.parametrize("name", ["setup.exe", "run.sh"])
def test_a_windows_or_posix_executable_is_refused_by_default_on_every_platform(tmp_path: Path, name: str) -> None:
    """The default blocked extensions are the Windows and the POSIX list together, on every host."""
    attachment = tmp_path / name
    attachment.write_bytes(b"x")
    transport = RecordingTransport()

    with pytest.raises(AttachmentSecurityError):
        send_email(
            config=VALID, recipients="ops@example.com", subject="s", attachments=[attachment], transport=transport
        )

    assert transport.attempted_hosts == []


@pytest.mark.os_agnostic
@pytest.mark.parametrize("host", ["smtp.example.com:+25", "smtp.example.com:2_5"])
def test_an_smtp_port_that_is_not_plain_digits_is_refused_with_one_line(host: str) -> None:
    """A port Python's int() would read is still refused, naming the host, not the input of other keys."""
    with pytest.raises(ValidationError) as refused:
        EmailConfig(smtp_hosts=[host])

    assert describe_validation_error(refused.value) == [f'email: invalid smtp port in "{host}"']
