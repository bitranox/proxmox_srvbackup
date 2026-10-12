"""Property-based tests for EmailConfig Pydantic model.

Uses hypothesis to verify that EmailConfig validation enforces its
contracts across a wide range of generated inputs: valid emails pass,
port numbers in range pass, and negative timeouts are rejected.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from proxmox_srvbackup.adapters.email.config import load_email_config_from_dict
from proxmox_srvbackup.adapters.email.sender import EmailConfig

# ======================== Strategy helpers ========================

# Generate syntactically valid email addresses: local@domain.tld
_email_local_part = st.from_regex(r"[a-z][a-z0-9_.]{0,20}", fullmatch=True)
_email_domain = st.from_regex(r"[a-z][a-z0-9]{0,10}\.[a-z]{2,4}", fullmatch=True)
_valid_email = st.builds(lambda local, domain: f"{local}@{domain}", _email_local_part, _email_domain)  # type: ignore[arg-type]

# Generate valid SMTP host strings: hostname:port or hostname
_hostname = st.from_regex(r"[a-z][a-z0-9]{0,15}\.[a-z]{2,6}", fullmatch=True)
_port = st.integers(min_value=1, max_value=65535)
_smtp_host = st.builds(lambda h, p: f"{h}:{p}", _hostname, _port)  # type: ignore[arg-type]


# ======================== Valid email address tests ========================


@pytest.mark.os_agnostic
@given(email=_valid_email)
@settings(max_examples=100)
def test_valid_email_addresses_pass_from_address_validation(email: str) -> None:
    """Syntactically valid email addresses are accepted as from_address."""
    config = EmailConfig(from_address=email)

    assert config.from_address == email


@pytest.mark.os_agnostic
@given(email=_valid_email)
@settings(max_examples=100)
def test_valid_email_addresses_pass_recipients_validation(email: str) -> None:
    """Syntactically valid email addresses are accepted in the recipients list."""
    config = EmailConfig(recipients=[email])

    assert config.recipients == [email]


@pytest.mark.os_agnostic
@given(emails=st.lists(_valid_email, min_size=1, max_size=5))
@settings(max_examples=50)
def test_multiple_valid_recipients_pass_validation(emails: list[str]) -> None:
    """Multiple syntactically valid email addresses are accepted in recipients."""
    config = EmailConfig(recipients=emails)

    assert config.recipients == emails


# ======================== Valid SMTP host tests ========================


@pytest.mark.os_agnostic
@given(host=_smtp_host)
@settings(max_examples=100)
def test_valid_smtp_hosts_pass_validation(host: str) -> None:
    """SMTP hosts in 'hostname:port' format are accepted."""
    config = EmailConfig(smtphosts=[host])

    assert config.smtphosts == [host]


@pytest.mark.os_agnostic
@given(port=st.integers(min_value=1, max_value=65535))
@settings(max_examples=50)
def test_port_numbers_in_valid_range_pass_validation(port: int) -> None:
    """Port numbers between 1 and 65535 are accepted in SMTP host strings."""
    host = f"smtp.example.com:{port}"

    config = EmailConfig(smtphosts=[host])

    assert config.smtphosts == [host]


# ======================== Timeout validation tests ========================


@pytest.mark.os_agnostic
@given(timeout=st.floats(max_value=0.0, allow_nan=False, allow_infinity=False))
@settings(max_examples=100)
def test_non_positive_timeouts_are_rejected(timeout: float) -> None:
    """Timeouts that are zero or negative are rejected by the model validator."""
    with pytest.raises(ValidationError, match="timeout must be positive"):
        EmailConfig(smtp_timeout=timeout)


@pytest.mark.os_agnostic
@given(timeout=st.floats(min_value=0.001, max_value=3600.0, allow_nan=False, allow_infinity=False))
@settings(max_examples=100)
def test_positive_timeouts_pass_validation(timeout: float) -> None:
    """Positive timeout values are accepted."""
    config = EmailConfig(smtp_timeout=timeout)

    assert config.smtp_timeout == timeout


# ======================== Boolean field tests ========================


@pytest.mark.os_agnostic
@given(use_starttls=st.booleans())
def test_use_starttls_accepts_any_boolean(use_starttls: bool) -> None:
    """The use_starttls field accepts both True and False."""
    config = EmailConfig(smtp_use_starttls=use_starttls)

    assert config.smtp_use_starttls is use_starttls


# ======================== Empty/None from_address tests ========================


@pytest.mark.os_agnostic
@given(whitespace=st.from_regex(r"\s*", fullmatch=True))
@settings(max_examples=50)
def test_whitespace_only_from_address_coerces_to_none(whitespace: str) -> None:
    """A whitespace-only from_address in the configuration means not configured."""
    config = load_email_config_from_dict({"email": {"from_address": whitespace}})

    assert config.from_address is None


# ======================== Runtime recipient validation tests ========================


@pytest.mark.os_agnostic
@given(invalid_email=st.from_regex(r"[a-z]{1,10}", fullmatch=True))
@settings(max_examples=50)
def test_invalid_runtime_recipients_are_rejected_in_memory_adapter(invalid_email: str) -> None:
    """Invalid runtime recipients raise InvalidRecipientError in memory adapter."""
    from proxmox_srvbackup.adapters.memory.email import EmailSpy
    from proxmox_srvbackup.domain.errors import InvalidRecipientError

    config = EmailConfig(smtphosts=["smtp.example.com:587"])
    spy = EmailSpy()

    with pytest.raises(InvalidRecipientError, match="Invalid recipient"):
        spy.send_email(
            config=config,
            recipients=invalid_email,
            subject="Test",
            body="Test body",
        )


@pytest.mark.os_agnostic
@given(invalid_email=st.from_regex(r"[a-z]{1,10}", fullmatch=True))
@settings(max_examples=50)
def test_invalid_runtime_recipients_are_rejected_in_notification(invalid_email: str) -> None:
    """Invalid runtime recipients raise InvalidRecipientError in notification adapter."""
    from proxmox_srvbackup.adapters.memory.email import EmailSpy
    from proxmox_srvbackup.domain.errors import InvalidRecipientError

    config = EmailConfig(smtphosts=["smtp.example.com:587"])
    spy = EmailSpy()

    with pytest.raises(InvalidRecipientError, match="Invalid recipient"):
        spy.send_notification(
            config=config,
            recipients=invalid_email,
            subject="Test",
            message="Test message",
        )


# ======================== Attachment security settings tests ========================


# Strategy for file extensions (lowercase, 1-8 chars, no dots)
_extension = st.from_regex(r"[a-z]{1,8}", fullmatch=True)


@pytest.mark.os_agnostic
@given(extensions=st.lists(_extension, min_size=0, max_size=10))
@settings(max_examples=50)
def test_attachment_allowed_extensions_accepts_frozenset(extensions: list[str]) -> None:
    """Frozenset of extensions is accepted for attachment_allowed_extensions, dot-prefixed by ConfMail."""
    config = EmailConfig(attachment_allowed_extensions=frozenset(extensions))

    assert config.attachment_allowed_extensions == frozenset(f".{extension}" for extension in extensions)


@pytest.mark.os_agnostic
@given(extensions=st.lists(_extension, min_size=1, max_size=10))
@settings(max_examples=50)
def test_attachment_blocked_extensions_accepts_frozenset(extensions: list[str]) -> None:
    """Frozenset of extensions is accepted for attachment_blocked_extensions, dot-prefixed by ConfMail."""
    config = EmailConfig(attachment_blocked_extensions=frozenset(extensions))

    assert config.attachment_blocked_extensions == frozenset(f".{extension}" for extension in extensions)


@pytest.mark.os_agnostic
@given(extensions=st.lists(_extension, min_size=0, max_size=5))
@settings(max_examples=50)
def test_attachment_extensions_list_coerces_to_frozenset(extensions: list[str]) -> None:
    """A configured list of extensions becomes a frozenset; an empty one means the library defaults."""
    config = load_email_config_from_dict({"email": {"attachments": {"allowed_extensions": extensions}}})

    if extensions:
        assert config.attachment_allowed_extensions == frozenset(f".{extension}" for extension in extensions)
    else:
        assert config.attachment_allowed_extensions is None


@pytest.mark.os_agnostic
@given(max_size=st.integers(min_value=1, max_value=100_000_000))
@settings(max_examples=50)
def test_attachment_max_size_bytes_accepts_positive_integers(max_size: int) -> None:
    """Positive integers are accepted for attachment_max_size_bytes."""
    config = EmailConfig(attachment_max_size_bytes=max_size)

    assert config.attachment_max_size_bytes == max_size


@pytest.mark.os_agnostic
def test_attachment_max_size_bytes_zero_coerces_to_none() -> None:
    """A configured max_size_bytes of 0 means no size limit."""
    config = load_email_config_from_dict({"email": {"attachments": {"max_size_bytes": 0}}})

    assert config.attachment_max_size_bytes is None


@pytest.mark.os_agnostic
@given(allow_symlinks=st.booleans())
def test_attachment_allow_symlinks_accepts_any_boolean(allow_symlinks: bool) -> None:
    """The attachment_allow_symlinks field accepts both True and False."""
    config = EmailConfig(attachment_allow_symlinks=allow_symlinks)

    assert config.attachment_allow_symlinks is allow_symlinks


@pytest.mark.os_agnostic
@given(raise_on_violation=st.booleans())
def test_attachment_raise_on_security_violation_accepts_any_boolean(raise_on_violation: bool) -> None:
    """The attachment_raise_on_security_violation field accepts both True and False."""
    config = EmailConfig(attachment_raise_on_security_violation=raise_on_violation)

    assert config.attachment_raise_on_security_violation is raise_on_violation


@pytest.mark.os_agnostic
def test_attachment_allowed_directories_accepts_frozenset_of_paths() -> None:
    """Frozenset of Path objects is accepted for attachment_allowed_directories."""
    from pathlib import Path

    paths = frozenset([Path("/tmp"), Path("/home/user/docs")])
    config = EmailConfig(attachment_allowed_directories=paths)

    assert config.attachment_allowed_directories == paths


@pytest.mark.os_agnostic
def test_attachment_directories_list_coerces_to_frozenset() -> None:
    """List of path strings is coerced to frozenset of Paths."""
    from pathlib import Path

    paths = ["/tmp", "/home/user"]
    config = EmailConfig(attachment_allowed_directories=paths)  # type: ignore[arg-type]

    assert config.attachment_allowed_directories == frozenset([Path("/tmp"), Path("/home/user")])


@pytest.mark.os_agnostic
def test_attachment_directories_empty_list_coerces_to_none() -> None:
    """A configured empty directory list means the library defaults."""
    config = load_email_config_from_dict({"email": {"attachments": {"allowed_directories": []}}})

    assert config.attachment_allowed_directories is None
