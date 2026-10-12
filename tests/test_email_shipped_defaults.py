"""The template's shipped [email] defaults keep the library's attachment protection on.

The shipped file writes [] for the four attachment lists, meaning "the library's defaults".
For ConfMail an empty allowed list allows nothing and an empty blocked list blocks nothing,
so the translation must drop them: a dangerous attachment is refused and an ordinary one
delivered, both with the shipped file read as it ships.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any

import pytest
import rtoml
from btx_lib_mail import AttachmentSecurityError, AttachmentViolation, ConfMail

from proxmox_srvbackup.adapters.email.config import EmailConfig, load_email_config_from_dict
from proxmox_srvbackup.adapters.email.transport import send_email

if TYPE_CHECKING:
    from collections.abc import Iterator

    from btx_lib_mail.lib_mail import DeliveryOptions

_SHIPPED = (
    Path(__file__).parent.parent
    / "src"
    / "proxmox_srvbackup"
    / "adapters"
    / "config"
    / "defaultconfig.d"
    / "50-mail.toml"
)


class _Recording:
    def __init__(self) -> None:
        self.recipients: list[str] = []

    def deliver(self, *, host: str, sender: str, recipient: str, message: IO[bytes], delivery: DeliveryOptions) -> None:
        self.recipients.append(recipient)


def _shipped_config() -> EmailConfig:
    shipped: dict[str, Any] = rtoml.load(_SHIPPED)
    assert shipped["email"]["attachments"]["blocked_extensions"] == []  # the premise
    shipped["email"]["smtp_hosts"] = ["smtp.example.com:25"]
    return load_email_config_from_dict(shipped)


def _send(config: EmailConfig, attachment: Path, transport: _Recording) -> bool:
    return send_email(
        config=config,
        recipients="ops@example.com",
        subject="s",
        from_address="app@example.com",
        attachments=[attachment],
        transport=transport,
    )


def _a_file_in_a_blocked_directory() -> Path:
    for directory in sorted(ConfMail().attachment_blocked_directories):
        if not directory.is_dir():
            continue
        for entry in sorted(directory.iterdir()):
            if entry.is_file() and not entry.is_symlink():
                return entry
    raise AssertionError("no regular file directly inside any default blocked directory on this OS")


def _is_blocked(directory: Path) -> bool:
    resolved = directory.resolve()
    return any(resolved.is_relative_to(blocked.resolve()) for blocked in ConfMail().attachment_blocked_directories)


@pytest.fixture
def unblocked_dir(tmp_path: Path) -> Iterator[Path]:
    """A fresh directory under no default blocked directory, so only the file itself is judged.

    pytest's tmp_path is under /var on macOS (/private/var/folders), which the defaults block,
    so the first base that is not blocked is used: tmp_path, the home directory, the cwd.
    """
    base = next((base for base in (tmp_path, Path.home(), Path.cwd()) if not _is_blocked(base)), None)
    assert base is not None, "no candidate directory is outside the default blocked directories"
    directory = Path(tempfile.mkdtemp(prefix="shipped-defaults-", dir=base))
    yield directory
    shutil.rmtree(directory, ignore_errors=True)


@pytest.mark.os_agnostic
def test_a_dangerous_extension_is_refused_with_the_shipped_defaults(unblocked_dir: Path) -> None:
    extension = sorted(ConfMail().attachment_blocked_extensions)[0]
    attachment = unblocked_dir / f"payload{extension}"
    attachment.write_bytes(b"x")
    transport = _Recording()

    with pytest.raises(AttachmentSecurityError) as refused:
        _send(_shipped_config(), attachment, transport)

    # The blacklist must be what refused it: an empty allowlist passed through would refuse
    # every extension too, with "not in allowed list".
    assert refused.value.violation_type is AttachmentViolation.EXTENSION
    assert "is blocked" in refused.value.reason
    assert transport.recipients == []


@pytest.mark.os_agnostic
def test_a_file_in_a_blocked_directory_is_refused_with_the_shipped_defaults() -> None:
    transport = _Recording()

    with pytest.raises(AttachmentSecurityError) as refused:
        _send(_shipped_config(), _a_file_in_a_blocked_directory(), transport)

    # As above: "under blocked directory", not "not under any allowed directory".
    assert refused.value.violation_type is AttachmentViolation.DIRECTORY
    assert "under blocked directory" in refused.value.reason
    assert transport.recipients == []


@pytest.mark.os_agnostic
def test_an_ordinary_attachment_is_delivered_with_the_shipped_defaults(unblocked_dir: Path) -> None:
    attachment = unblocked_dir / "report.txt"
    attachment.write_text("ok", encoding="utf-8")
    transport = _Recording()

    assert _send(_shipped_config(), attachment, transport) is True
    assert transport.recipients == ["ops@example.com"]
