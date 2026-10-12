"""Email functionality stories: every sending scenario a single verse.

Verify that the mail wrapper correctly integrates btx_lib_mail with the
application's configuration system and provides a clean interface for
email operations.
"""

from __future__ import annotations

import smtplib
from dataclasses import dataclass
from pathlib import Path
from typing import IO, TYPE_CHECKING
from unittest.mock import patch

import pytest
import rtoml
from btx_lib_mail import ConfMail
from pydantic import SecretStr
from pydantic import ValidationError as PydanticValidationError

from proxmox_srvbackup.adapters.cli.commands.email._common import EmailConfigOverrides, apply_validated_overrides
from proxmox_srvbackup.adapters.email.sender import (
    EmailConfig,
    load_email_config_from_dict,
    send_email,
    send_notification,
)
from proxmox_srvbackup.domain.errors import ConfigurationError, DeliveryError

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from btx_lib_mail.lib_mail import DeliveryOptions

# ======================== Transport test double ========================


@dataclass(frozen=True)
class _Delivery:
    """One message the transport was asked to deliver."""

    host: str
    sender: str
    recipient: str
    payload: bytes
    credentials: tuple[str, str] | None
    local_hostname: str | None
    starttls_verify: bool
    deadline: float | None


class RecordingTransport:
    """btx_lib_mail ``Transport`` double that records deliveries instead of sending.

    Injected via the ``transport`` parameter rather than monkeypatching
    :mod:`smtplib`, so these tests assert on delivery intent (who, where, what)
    and stay independent of the library's wire protocol (DATA vs BDAT).

    Hosts named in ``failing_hosts`` raise on delivery, which drives the
    library's host-failover path without opening a socket.
    """

    def __init__(self, failing_hosts: Iterable[str] = (), failure: Exception | None = None) -> None:
        self.deliveries: list[_Delivery] = []
        self.attempted_hosts: list[str] = []
        self._failing_hosts = frozenset(failing_hosts)
        self._failure = failure

    def deliver(
        self,
        *,
        host: str,
        sender: str,
        recipient: str,
        message: IO[bytes],
        delivery: DeliveryOptions,
    ) -> None:
        """Record the attempt, or raise when ``host`` is configured to fail."""
        self.attempted_hosts.append(host)
        if host in self._failing_hosts:
            raise self._failure or smtplib.SMTPConnectError(421, f"simulated failure for {host}")
        self.deliveries.append(
            _Delivery(
                host=host,
                sender=sender,
                recipient=recipient,
                payload=message.read(),
                credentials=delivery.credentials,
                local_hostname=delivery.local_hostname,
                starttls_verify=delivery.starttls_verify,
                deadline=delivery.deadline,
            )
        )

    @property
    def recipients(self) -> list[str]:
        """Recipients that were successfully delivered to, in order."""
        return [delivery.recipient for delivery in self.deliveries]


# ======================== EmailConfig Default Values ========================


@pytest.mark.os_agnostic
def test_email_config_default_smtp_hosts_is_empty_list() -> None:
    """Default EmailConfig has an empty smtp_hosts list."""
    assert EmailConfig().smtphosts == []


@pytest.mark.os_agnostic
def test_email_config_default_from_address_is_none() -> None:
    """Default EmailConfig has from_address set to None."""
    assert EmailConfig().from_address is None


@pytest.mark.os_agnostic
def test_email_config_default_credentials_are_none() -> None:
    """Default EmailConfig has username and password set to None."""
    config = EmailConfig()
    assert config.smtp_username is None
    assert config.smtp_password is None


@pytest.mark.os_agnostic
def test_email_config_default_use_starttls_is_true() -> None:
    """Default EmailConfig enables STARTTLS."""
    assert EmailConfig().smtp_use_starttls is True


@pytest.mark.os_agnostic
def test_email_config_default_timeout_is_thirty_seconds() -> None:
    """Default EmailConfig uses a 30-second timeout."""
    assert EmailConfig().smtp_timeout == 30.0


@pytest.mark.os_agnostic
def test_email_config_default_raises_on_missing_attachments() -> None:
    """Default EmailConfig raises on missing attachments."""
    assert EmailConfig().raise_on_missing_attachments is True


@pytest.mark.os_agnostic
def test_email_config_default_raises_on_invalid_recipient() -> None:
    """Default EmailConfig raises on invalid recipients."""
    assert EmailConfig().raise_on_invalid_recipient is True


@pytest.mark.os_agnostic
def test_email_config_accepts_custom_values() -> None:
    """When custom values provided, EmailConfig stores them correctly."""
    config = EmailConfig(
        smtphosts=["smtp.example.com:587"],
        from_address="test@example.com",
        recipients=["admin@example.com", "ops@example.com"],
        smtp_username="user",
        smtp_password=SecretStr("pass"),
        smtp_use_starttls=False,
        smtp_timeout=60.0,
    )

    assert config.smtphosts == ["smtp.example.com:587"]
    assert config.from_address == "test@example.com"
    assert config.recipients == ["admin@example.com", "ops@example.com"]
    assert config.smtp_username == "user"
    assert config.smtp_password is not None
    assert config.smtp_password.get_secret_value() == "pass"
    assert config.smtp_use_starttls is False
    assert config.smtp_timeout == 60.0


@pytest.mark.os_agnostic
def test_email_config_is_immutable() -> None:
    """Once created, EmailConfig cannot be modified."""
    config = EmailConfig()

    with pytest.raises(PydanticValidationError):
        config.smtphosts = ["new.smtp.com"]  # type: ignore[misc]


# ======================== EmailConfig Validation ========================


@pytest.mark.os_agnostic
def test_email_config_rejects_negative_timeout() -> None:
    """Negative timeout values are caught early with clear error."""
    with pytest.raises(PydanticValidationError, match="timeout must be positive"):
        EmailConfig(smtp_timeout=-5.0)


@pytest.mark.os_agnostic
def test_email_config_rejects_zero_timeout() -> None:
    """Zero timeout is rejected as it would cause immediate failures."""
    with pytest.raises(PydanticValidationError, match="timeout must be positive"):
        EmailConfig(smtp_timeout=0.0)


@pytest.mark.os_agnostic
def test_email_config_rejects_invalid_from_address() -> None:
    """From address without @ is caught early with clear error."""
    with pytest.raises(PydanticValidationError, match="invalid email address"):
        EmailConfig(from_address="not-an-email")


@pytest.mark.os_agnostic
def test_email_config_rejects_malformed_smtp_host_port() -> None:
    """SMTP host with invalid host:port format is rejected."""
    with pytest.raises(PydanticValidationError, match="invalid smtp port"):
        EmailConfig(smtphosts=["smtp.test.com:587:extra"])


@pytest.mark.os_agnostic
def test_email_config_rejects_non_numeric_port() -> None:
    """Port must be a number, not text."""
    with pytest.raises(PydanticValidationError, match="invalid smtp port"):
        EmailConfig(smtphosts=["smtp.test.com:abc"])


@pytest.mark.os_agnostic
def test_email_config_rejects_port_above_65535() -> None:
    """Port must be within valid TCP range."""
    with pytest.raises(PydanticValidationError, match="port must be 1-65535"):
        EmailConfig(smtphosts=["smtp.test.com:99999"])


@pytest.mark.os_agnostic
def test_email_config_rejects_port_below_1() -> None:
    """Port 0 is reserved and invalid."""
    with pytest.raises(PydanticValidationError, match="port must be 1-65535"):
        EmailConfig(smtphosts=["smtp.test.com:0"])


@pytest.mark.os_agnostic
def test_email_config_accepts_host_without_port() -> None:
    """SMTP host without explicit port uses default."""
    config = EmailConfig(smtphosts=["smtp.test.com"])
    assert config.smtphosts == ["smtp.test.com"]


@pytest.mark.os_agnostic
def test_email_config_accepts_host_with_valid_port() -> None:
    """SMTP host with standard port is accepted."""
    config = EmailConfig(smtphosts=["smtp.test.com:587"])
    assert config.smtphosts == ["smtp.test.com:587"]


@pytest.mark.os_agnostic
def test_email_config_accepts_ipv6_bracketed_host_with_port() -> None:
    """Bracketed IPv6 address with port is accepted."""
    config = EmailConfig(smtphosts=["[::1]:25"])
    assert config.smtphosts == ["[::1]:25"]


@pytest.mark.os_agnostic
def test_email_config_accepts_ipv6_bracketed_host_without_port() -> None:
    """Bracketed IPv6 address without port is accepted."""
    config = EmailConfig(smtphosts=["[::1]"])
    assert config.smtphosts == ["[::1]"]


@pytest.mark.os_agnostic
def test_email_config_accepts_full_ipv6_bracketed_host() -> None:
    """Full bracketed IPv6 address with port is accepted."""
    config = EmailConfig(smtphosts=["[2001:db8::1]:587"])
    assert config.smtphosts == ["[2001:db8::1]:587"]


@pytest.mark.os_agnostic
def test_email_config_rejects_ipv6_missing_closing_bracket() -> None:
    """Bracketed IPv6 without closing bracket is rejected."""
    with pytest.raises(PydanticValidationError, match="missing closing bracket"):
        EmailConfig(smtphosts=["[::1"])


@pytest.mark.os_agnostic
def test_email_config_rejects_ipv6_invalid_port() -> None:
    """Bracketed IPv6 with non-numeric port is rejected."""
    with pytest.raises(PydanticValidationError, match="invalid smtp port"):
        EmailConfig(smtphosts=["[::1]:abc"])


@pytest.mark.os_agnostic
def test_email_config_accepts_none_from_address() -> None:
    """None from_address is valid (not configured)."""
    config = EmailConfig()
    assert config.from_address is None


@pytest.mark.os_agnostic
def test_email_config_rejects_bare_at_sign() -> None:
    """A bare @ is not a valid email address."""
    with pytest.raises(PydanticValidationError, match="invalid email address"):
        EmailConfig(from_address="@")


@pytest.mark.os_agnostic
def test_email_config_rejects_missing_domain() -> None:
    """An email without a domain part is rejected."""
    with pytest.raises(PydanticValidationError, match="invalid email address"):
        EmailConfig(from_address="user@")


@pytest.mark.os_agnostic
def test_email_config_rejects_missing_local_part() -> None:
    """An email without a local part is rejected."""
    with pytest.raises(PydanticValidationError, match="invalid email address"):
        EmailConfig(from_address="@domain.com")


@pytest.mark.os_agnostic
def test_email_config_rejects_double_at_sign() -> None:
    """An email with multiple @ signs is rejected."""
    with pytest.raises(PydanticValidationError, match="invalid email address"):
        EmailConfig(from_address="a@@b.com")


# ======================== EmailConfig lists ========================


@pytest.mark.os_agnostic
def test_email_config_preserves_list_smtp_hosts() -> None:
    """List smtp_hosts is preserved unchanged."""
    config = EmailConfig(smtphosts=["smtp1.example.com:587", "smtp2.example.com:25"])
    assert config.smtphosts == ["smtp1.example.com:587", "smtp2.example.com:25"]


@pytest.mark.os_agnostic
def test_email_config_preserves_list_recipients() -> None:
    """List recipients is preserved unchanged."""
    config = EmailConfig(recipients=["a@example.com", "b@example.com"])
    assert config.recipients == ["a@example.com", "b@example.com"]


_PASSWORD = "s3cr3t-value"


def _dumped_json(config: EmailConfig) -> str:
    return config.model_dump_json()


def _dumped_python(config: EmailConfig) -> str:
    return str(config.model_dump())


def _instance_vars(config: EmailConfig) -> str:
    return str(vars(config))


@pytest.mark.os_agnostic
@pytest.mark.parametrize(
    "render",
    [str, repr, format, _dumped_json, _dumped_python, _instance_vars],
    ids=["str", "repr", "format", "model_dump_json", "model_dump", "vars"],
)
def test_no_rendering_of_the_email_config_shows_the_password(render: Callable[[EmailConfig], str]) -> None:
    """A config reaching a log line, an error message or a JSON dump must not carry the password.

    Loaded the way a config file supplies it: a plain string.
    """
    config = load_email_config_from_dict(
        {"email": {"smtp_hosts": ["smtp.example.com:587"], "smtp_username": "user", "smtp_password": _PASSWORD}}
    )

    assert _PASSWORD not in render(config)


@pytest.mark.os_agnostic
def test_an_override_keeps_the_configured_password() -> None:
    config = EmailConfig(smtphosts=["smtp.example.com:587"], smtp_username="user", smtp_password=SecretStr(_PASSWORD))

    overridden = apply_validated_overrides(config, EmailConfigOverrides.from_cli_options(timeout=5.0))

    assert overridden.smtp_password is not None
    assert overridden.smtp_password.get_secret_value() == _PASSWORD
    assert overridden.smtp_timeout == 5.0


@pytest.mark.os_agnostic
def test_no_override_given_returns_the_configuration_itself() -> None:
    config = EmailConfig(smtphosts=["smtp.example.com:587"])

    assert apply_validated_overrides(config, EmailConfigOverrides.from_cli_options()) is config


@pytest.mark.os_agnostic
def test_an_unset_host_option_keeps_the_hosts_and_a_set_one_replaces_them() -> None:
    config = EmailConfig(smtphosts=["smtp.example.com:587"])

    unset = apply_validated_overrides(config, EmailConfigOverrides.from_cli_options(smtp_hosts=()))
    replaced = apply_validated_overrides(
        config, EmailConfigOverrides.from_cli_options(smtp_hosts=("other.example.com:25", "third.example.com:25"))
    )

    assert unset.smtphosts == ["smtp.example.com:587"]
    assert replaced.smtphosts == ["other.example.com:25", "third.example.com:25"]


@pytest.mark.os_agnostic
def test_a_password_given_on_the_command_line_never_renders_from_the_overrides() -> None:
    overrides = EmailConfigOverrides.from_cli_options(smtp_password=_PASSWORD)

    assert _PASSWORD not in repr(overrides)
    assert _PASSWORD not in str(overrides.model_dump())
    assert overrides.smtp_password is not None
    assert overrides.smtp_password.get_secret_value() == _PASSWORD


@pytest.mark.os_agnostic
def test_an_override_refuses_a_name_that_is_not_an_email_config_field() -> None:
    """The overrides carry EmailConfig's own field names, so a renamed field cannot pass unnoticed."""
    with pytest.raises(PydanticValidationError, match="smtp_hosts"):
        EmailConfigOverrides.model_validate({"smtp_hosts": ["smtp.example.com:587"]})


@pytest.mark.os_agnostic
def test_each_command_line_option_lands_in_its_own_field() -> None:
    """Every option is distinct from its neighbours, so a swapped parameter shows as a mismatch."""
    overrides = EmailConfigOverrides.from_cli_options(
        smtp_hosts=("smtp.example.com:587",),
        smtp_username="user",
        smtp_password=_PASSWORD,
        use_starttls=False,
        timeout=7.5,
        raise_on_missing_attachments=True,
        raise_on_invalid_recipient=False,
    )

    dumped = overrides.model_dump()
    secret = dumped.pop("smtp_password")

    assert secret.get_secret_value() == _PASSWORD
    assert dumped == {
        "smtphosts": ("smtp.example.com:587",),
        "smtp_username": "user",
        "smtp_use_starttls": False,
        "smtp_timeout": 7.5,
        "raise_on_missing_attachments": True,
        "raise_on_invalid_recipient": False,
    }


@pytest.mark.os_agnostic
def test_a_refused_password_value_stays_out_of_the_error_details() -> None:
    with pytest.raises(PydanticValidationError) as caught:
        EmailConfigOverrides.model_validate({"smtp_password": [_PASSWORD]})

    assert _PASSWORD not in str(caught.value.errors())
    assert _PASSWORD not in caught.value.json()


@pytest.mark.os_agnostic
def test_every_override_names_an_email_config_field() -> None:
    assert set(EmailConfigOverrides.model_fields) <= set(EmailConfig.model_fields)


# ======================== load_email_config_from_dict ========================


@pytest.mark.os_agnostic
def test_load_config_returns_defaults_when_email_section_missing() -> None:
    """Missing email section falls back to safe defaults."""
    config = load_email_config_from_dict({})

    assert config.smtphosts == []
    assert config.from_address is None


@pytest.mark.os_agnostic
def test_load_config_extracts_values_from_email_section() -> None:
    """Email section values are correctly extracted and typed."""
    config_dict = {
        "email": {
            "smtp_hosts": ["smtp.test.com:587"],
            "from_address": "alerts@test.com",
            "smtp_username": "testuser",
            "smtp_password": "testpass",
            "use_starttls": False,
            "timeout": 120.0,
        }
    }

    config = load_email_config_from_dict(config_dict)

    assert config.smtphosts == ["smtp.test.com:587"]
    assert config.from_address == "alerts@test.com"
    assert config.smtp_username == "testuser"
    assert config.smtp_password is not None
    assert config.smtp_password.get_secret_value() == "testpass"
    assert config.smtp_use_starttls is False
    assert config.smtp_timeout == 120.0


@pytest.mark.os_agnostic
def test_load_config_merges_partial_config_with_defaults() -> None:
    """Partial config inherits defaults for unspecified values."""
    config_dict = {
        "email": {
            "smtp_hosts": ["smtp.partial.com"],
            "from_address": "partial@test.com",
        }
    }

    config = load_email_config_from_dict(config_dict)

    assert config.smtphosts == ["smtp.partial.com"]
    assert config.from_address == "partial@test.com"
    assert config.smtp_username is None
    assert config.smtp_use_starttls is True


@pytest.mark.os_agnostic
def test_load_config_rejects_non_dict_email_section() -> None:
    """Non-dict email section raises ValidationError."""
    config_dict = {"email": "invalid"}

    with pytest.raises(PydanticValidationError):
        load_email_config_from_dict(config_dict)


@pytest.mark.os_agnostic
def test_load_config_rejects_malformed_timeout() -> None:
    """Invalid timeout string raises ValidationError."""
    config_dict = {"email": {"timeout": "not_a_number"}}

    with pytest.raises(PydanticValidationError):
        load_email_config_from_dict(config_dict)


@pytest.mark.os_agnostic
def test_load_config_coerces_string_smtp_hosts_to_list() -> None:
    """String smtp_hosts is coerced to single-element list."""
    config_dict = {"email": {"smtp_hosts": "smtp.example.com:587"}}

    email_config = load_email_config_from_dict(config_dict)

    assert email_config.smtphosts == ["smtp.example.com:587"]


@pytest.mark.os_agnostic
def test_load_config_uses_default_for_string_boolean() -> None:
    """String boolean value falls back to default."""
    config_dict = {"email": {"use_starttls": "yes"}}

    email_config = load_email_config_from_dict(config_dict)

    assert email_config.smtp_use_starttls is True


@pytest.mark.os_agnostic
def test_load_config_coerces_empty_from_address_to_none() -> None:
    """Empty string from_address is coerced to None."""
    config_dict = {"email": {"from_address": ""}}

    config = load_email_config_from_dict(config_dict)

    assert config.from_address is None


@pytest.mark.os_agnostic
def test_load_config_coerces_empty_string_username_to_none() -> None:
    """Empty string username is coerced to None (prevents empty auth attempts)."""
    config_dict = {"email": {"smtp_username": ""}}

    email_config = load_email_config_from_dict(config_dict)

    assert email_config.smtp_username is None


@pytest.mark.os_agnostic
def test_load_config_coerces_empty_string_password_to_none() -> None:
    """Empty string password is coerced to None (prevents empty auth attempts)."""
    config_dict = {"email": {"smtp_password": ""}}

    email_config = load_email_config_from_dict(config_dict)

    assert email_config.smtp_password is None


@pytest.mark.os_agnostic
def test_load_config_coerces_whitespace_username_to_none() -> None:
    """Whitespace-only username is coerced to None."""
    config_dict = {"email": {"smtp_username": "   "}}

    email_config = load_email_config_from_dict(config_dict)

    assert email_config.smtp_username is None


@pytest.mark.os_agnostic
def test_load_config_rejects_mixed_invalid_values() -> None:
    """Mixed valid/invalid config raises ValidationError for invalid fields."""
    config_dict = {
        "email": {
            "smtp_hosts": ["smtp.test.com:587"],
            "from_address": "test@example.com",
            "timeout": "invalid",
            "use_starttls": "maybe",
        }
    }

    with pytest.raises(PydanticValidationError):
        load_email_config_from_dict(config_dict)


# ======================== send_email ========================


@pytest.mark.os_agnostic
def test_send_email_delivers_simple_message() -> None:
    """Basic email with required fields is sent successfully."""
    config = EmailConfig(
        smtphosts=["smtp.test.com:587"],
        from_address="sender@test.com",
    )

    transport = RecordingTransport()
    result = send_email(
        config=config,
        recipients="recipient@test.com",
        subject="Test Subject",
        body="Test body",
        transport=transport,
    )

    assert result is True
    assert transport.recipients == ["recipient@test.com"]
    assert transport.deliveries[0].sender == "sender@test.com"
    assert transport.deliveries[0].host == "smtp.test.com:587"
    assert b"Test body" in transport.deliveries[0].payload


@pytest.mark.os_agnostic
def test_send_email_includes_html_body() -> None:
    """Email with both plain text and HTML is sent as multipart."""
    config = EmailConfig(
        smtphosts=["smtp.test.com:587"],
        from_address="sender@test.com",
    )

    transport = RecordingTransport()
    result = send_email(
        config=config,
        recipients="recipient@test.com",
        subject="Test Subject",
        body="Plain text",
        body_html="<h1>HTML</h1>",
        transport=transport,
    )

    assert result is True
    payload = transport.deliveries[0].payload
    assert b"multipart/alternative" in payload
    assert b"text/html" in payload


@pytest.mark.os_agnostic
def test_send_email_accepts_multiple_recipients() -> None:
    """Email can be sent to multiple recipients at once."""
    config = EmailConfig(
        smtphosts=["smtp.test.com:587"],
        from_address="sender@test.com",
    )

    transport = RecordingTransport()
    result = send_email(
        config=config,
        recipients=["user1@test.com", "user2@test.com"],
        subject="Test Subject",
        body="Test body",
        transport=transport,
    )

    assert result is True
    assert transport.recipients == ["user1@test.com", "user2@test.com"]


@pytest.mark.os_agnostic
def test_send_email_allows_sender_override() -> None:
    """from_address parameter overrides config default."""
    config = EmailConfig(
        smtphosts=["smtp.test.com:587"],
        from_address="default@test.com",
    )

    transport = RecordingTransport()
    result = send_email(
        config=config,
        recipients="recipient@test.com",
        subject="Test Subject",
        body="Test body",
        from_address="override@test.com",
        transport=transport,
    )

    assert result is True
    assert transport.deliveries[0].sender == "override@test.com"


@pytest.mark.os_agnostic
def test_send_email_includes_attachments(tmp_path: Path) -> None:
    """Email with file attachments is sent successfully."""
    attachment = tmp_path / "test.txt"
    attachment.write_text("Test attachment content")

    config = EmailConfig(
        smtphosts=["smtp.test.com:587"],
        from_address="sender@test.com",
        # Disable directory blocking for tests using tmp_path
        # (macOS tmp_path is under /var which is blocked by default)
        attachment_blocked_directories=frozenset(),
        attachment_allow_empty_blocklists=True,
    )

    transport = RecordingTransport()
    result = send_email(
        config=config,
        recipients="recipient@test.com",
        subject="Test Subject",
        body="Test body",
        attachments=[attachment],
        transport=transport,
    )

    assert result is True
    assert b"test.txt" in transport.deliveries[0].payload


@pytest.mark.os_agnostic
def test_send_email_uses_credentials_when_provided() -> None:
    """SMTP credentials are used when configured."""
    config = EmailConfig(
        smtphosts=["smtp.test.com:587"],
        from_address="sender@test.com",
        smtp_username="testuser",
        smtp_password=SecretStr("testpass"),
    )

    transport = RecordingTransport()
    result = send_email(
        config=config,
        recipients="recipient@test.com",
        subject="Test Subject",
        body="Test body",
        transport=transport,
    )

    assert result is True
    assert transport.deliveries[0].credentials == ("testuser", "testpass")


# ======================== send_notification ========================


@pytest.mark.os_agnostic
def test_send_notification_delivers_plain_text_message() -> None:
    """Notification sends plain-text email without HTML."""
    config = EmailConfig(
        smtphosts=["smtp.test.com:587"],
        from_address="alerts@test.com",
    )

    transport = RecordingTransport()
    result = send_notification(
        config=config,
        recipients="admin@test.com",
        subject="Alert",
        message="System notification",
        transport=transport,
    )

    assert result is True
    payload = transport.deliveries[0].payload
    assert b"System notification" in payload
    assert b"text/html" not in payload


@pytest.mark.os_agnostic
def test_send_notification_accepts_multiple_recipients() -> None:
    """Notification can be sent to multiple recipients."""
    config = EmailConfig(
        smtphosts=["smtp.test.com:587"],
        from_address="alerts@test.com",
    )

    transport = RecordingTransport()
    result = send_notification(
        config=config,
        recipients=["admin1@test.com", "admin2@test.com"],
        subject="Alert",
        message="System notification",
        transport=transport,
    )

    assert result is True
    assert transport.recipients == ["admin1@test.com", "admin2@test.com"]


@pytest.mark.os_agnostic
def test_send_notification_forwards_from_address_override() -> None:
    """When from_address is provided, notification uses it instead of config default."""
    config = EmailConfig(
        smtphosts=["smtp.test.com:587"],
        from_address="default@test.com",
    )

    transport = RecordingTransport()
    result = send_notification(
        config=config,
        recipients="admin@test.com",
        subject="Alert",
        message="System notification",
        from_address="override@test.com",
        transport=transport,
    )

    assert result is True
    # The override must reach the envelope sender, not just the rendered headers
    assert len(transport.deliveries) == 1
    assert transport.deliveries[0].sender == "override@test.com"


# ======================== send_email — from_address validation ========================


@pytest.mark.os_agnostic
def test_send_email_raises_when_no_smtp_hosts() -> None:
    """Empty SMTP hosts list raises ConfigurationError before attempting delivery."""
    config = EmailConfig(from_address="sender@test.com")
    with pytest.raises(ConfigurationError, match="No SMTP hosts configured"):
        send_email(
            config=config,
            recipients="recipient@test.com",
            subject="Test",
            body="Hello",
        )


@pytest.mark.os_agnostic
def test_send_email_raises_when_no_recipients() -> None:
    """Empty recipients sequence raises ValueError before attempting delivery."""
    config = EmailConfig(
        smtphosts=["smtp.test.com:587"],
        from_address="sender@test.com",
    )
    with pytest.raises(ValueError, match="No recipients configured and no override provided"):
        send_email(
            config=config,
            recipients=[],
            subject="Test",
            body="Hello",
        )


@pytest.mark.os_agnostic
def test_send_email_raises_when_no_from_address() -> None:
    """Missing from_address in both config and override raises ValueError."""
    config = EmailConfig(smtphosts=["smtp.test.com:587"])

    with pytest.raises(ValueError, match="No from_address configured"):
        send_email(
            config=config,
            recipients="recipient@test.com",
            subject="Test",
            body="Hello",
        )


# ======================== Error Scenarios ========================


@pytest.mark.os_agnostic
def test_send_email_raises_when_smtp_connection_fails() -> None:
    """SMTP connection failure raises DeliveryError."""
    config = EmailConfig(
        smtphosts=["smtp.test.com:587"],
        from_address="sender@test.com",
    )

    transport = RecordingTransport(failing_hosts=["smtp.test.com:587"])

    with pytest.raises(DeliveryError, match=r"failed.*on all of following hosts"):
        send_email(
            config=config,
            recipients="recipient@test.com",
            subject="Test",
            body="Hello",
            transport=transport,
        )


@pytest.mark.os_agnostic
def test_send_email_raises_when_authentication_fails() -> None:
    """SMTP authentication failure raises DeliveryError."""
    config = EmailConfig(
        smtphosts=["smtp.test.com:587"],
        from_address="sender@test.com",
        smtp_username="user@test.com",
        smtp_password=SecretStr("wrong_password"),
    )
    transport = RecordingTransport(
        failing_hosts=["smtp.test.com:587"],
        failure=smtplib.SMTPAuthenticationError(535, b"Authentication credentials invalid"),
    )

    with pytest.raises(DeliveryError, match=r"failed.*on all of following hosts"):
        send_email(
            config=config,
            recipients="recipient@test.com",
            subject="Test",
            body="Hello",
            transport=transport,
        )


@pytest.mark.os_agnostic
def test_send_email_raises_when_recipient_validation_fails() -> None:
    """Invalid recipient raises DeliveryError."""
    config = EmailConfig(
        smtphosts=["smtp.test.com:587"],
        from_address="sender@test.com",
    )

    transport = RecordingTransport(
        failing_hosts=["smtp.test.com:587"],
        failure=smtplib.SMTPRecipientsRefused({"recipient@test.com": (550, b"No such user")}),
    )

    with pytest.raises(DeliveryError, match="following recipients failed"):
        send_email(
            config=config,
            recipients="recipient@test.com",
            subject="Test",
            body="Hello",
            transport=transport,
        )


@pytest.mark.os_agnostic
def test_a_delivery_error_keeps_the_library_message_even_when_it_contains_a_keyword() -> None:
    """No keyword filter rewrites the message: a host named like ``key`` used to hide it."""
    host = "smtp.keystone.example:587"
    config = EmailConfig(smtphosts=[host], from_address="sender@test.com")

    with pytest.raises(DeliveryError) as failed:
        send_email(
            config=config,
            recipients="login@test.com",
            subject="Test",
            transport=RecordingTransport(failing_hosts=[host]),
        )

    assert "following recipients failed" in str(failed.value)
    assert host in str(failed.value)


@pytest.mark.os_agnostic
def test_send_email_raises_when_attachment_missing(tmp_path: Path) -> None:
    """Missing attachment raises FileNotFoundError when configured."""
    nonexistent = tmp_path / "nonexistent.txt"

    config = EmailConfig(
        smtphosts=["smtp.test.com:587"],
        from_address="sender@test.com",
        raise_on_missing_attachments=True,
        # Disable directory blocking for tests using tmp_path
        # (macOS tmp_path is under /var which is blocked by default)
        attachment_blocked_directories=frozenset(),
        attachment_allow_empty_blocklists=True,
    )

    with pytest.raises(FileNotFoundError):
        send_email(
            config=config,
            recipients="recipient@test.com",
            subject="Test",
            body="Hello",
            attachments=[nonexistent],
            transport=RecordingTransport(),
        )


@pytest.mark.os_agnostic
def test_send_email_raises_when_all_smtp_hosts_fail() -> None:
    """All SMTP hosts failing raises DeliveryError."""
    config = EmailConfig(
        smtphosts=["smtp1.test.com:587", "smtp2.test.com:587"],
        from_address="sender@test.com",
    )

    transport = RecordingTransport(failing_hosts=["smtp1.test.com:587", "smtp2.test.com:587"])

    with pytest.raises(DeliveryError, match="following recipients failed"):
        send_email(
            config=config,
            recipients="recipient@test.com",
            subject="Test",
            body="Hello",
            transport=transport,
        )

    assert transport.attempted_hosts == ["smtp1.test.com:587", "smtp2.test.com:587"]
    assert transport.deliveries == []


@pytest.mark.os_agnostic
def test_send_email_falls_back_to_second_host_when_first_fails() -> None:
    """When the first SMTP host fails, email is sent via the second host."""
    config = EmailConfig(
        smtphosts=["smtp1.test.com:587", "smtp2.test.com:587"],
        from_address="sender@test.com",
    )

    transport = RecordingTransport(failing_hosts=["smtp1.test.com:587"])

    result = send_email(
        config=config,
        recipients="recipient@test.com",
        subject="Fallback Test",
        body="Should arrive via second host",
        transport=transport,
    )

    assert result is True
    assert transport.attempted_hosts == ["smtp1.test.com:587", "smtp2.test.com:587"]
    assert [delivery.host for delivery in transport.deliveries] == ["smtp2.test.com:587"]


# ======================== EmailConfig Recipients Defaults ========================


@pytest.mark.os_agnostic
def test_email_config_default_recipients_is_empty_list() -> None:
    """Default EmailConfig has an empty recipients list."""
    assert EmailConfig().recipients == []


@pytest.mark.os_agnostic
def test_email_config_rejects_invalid_recipient_in_list() -> None:
    """Recipient without @ is caught early with clear error."""
    with pytest.raises(PydanticValidationError, match="invalid email address"):
        EmailConfig(recipients=["not-an-email"])


@pytest.mark.os_agnostic
def test_email_config_accepts_valid_recipients_list() -> None:
    """Valid recipient addresses are accepted."""
    config = EmailConfig(recipients=["admin@example.com", "ops@example.com"])
    assert config.recipients == ["admin@example.com", "ops@example.com"]


@pytest.mark.os_agnostic
def test_email_config_accepts_empty_recipients_list() -> None:
    """Empty recipients list is valid (not-configured sentinel)."""
    config = EmailConfig(recipients=[])
    assert config.recipients == []


# ======================== load_email_config_from_dict — recipients ========================


@pytest.mark.os_agnostic
def test_load_config_extracts_recipients_from_email_section() -> None:
    """Recipients are correctly extracted from config dict."""
    config_dict = {
        "email": {
            "recipients": ["admin@test.com", "ops@test.com"],
        }
    }

    config = load_email_config_from_dict(config_dict)

    assert config.recipients == ["admin@test.com", "ops@test.com"]


@pytest.mark.os_agnostic
def test_load_config_defaults_recipients_to_empty_list() -> None:
    """Missing recipients field defaults to empty list."""
    config_dict: dict[str, dict[str, object]] = {"email": {}}

    config = load_email_config_from_dict(config_dict)

    assert config.recipients == []


# ======================== send_email — recipients fallback ========================


@pytest.mark.os_agnostic
def test_send_email_uses_config_recipients_when_parameter_is_none() -> None:
    """When recipients parameter is None, config.recipients is used."""
    config = EmailConfig(
        smtphosts=["smtp.test.com:587"],
        from_address="sender@test.com",
        recipients=["default@test.com"],
    )

    transport = RecordingTransport()
    result = send_email(
        config=config,
        subject="Test Subject",
        body="Test body",
        transport=transport,
    )

    assert result is True
    assert transport.recipients == ["default@test.com"]


@pytest.mark.os_agnostic
def test_send_email_parameter_overrides_config_recipients() -> None:
    """When recipients parameter is provided, it replaces config recipients."""
    config = EmailConfig(
        smtphosts=["smtp.test.com:587"],
        from_address="sender@test.com",
        recipients=["config@test.com"],
    )

    transport = RecordingTransport()
    result = send_email(
        config=config,
        recipients="override@test.com",
        subject="Test Subject",
        body="Test body",
        transport=transport,
    )

    assert result is True
    assert transport.recipients == ["override@test.com"]


@pytest.mark.os_agnostic
def test_send_email_raises_when_no_recipients_configured_and_none_provided() -> None:
    """Both config and parameter missing recipients raises ValueError."""
    config = EmailConfig(
        smtphosts=["smtp.test.com:587"],
        from_address="sender@test.com",
    )

    with pytest.raises(ValueError, match="No recipients configured and no override provided"):
        send_email(
            config=config,
            subject="Test",
            body="Hello",
        )


@pytest.mark.os_agnostic
def test_send_email_raises_when_config_recipients_empty_and_none_provided() -> None:
    """Explicit empty config recipients with None parameter raises ValueError."""
    config = EmailConfig(
        smtphosts=["smtp.test.com:587"],
        from_address="sender@test.com",
        recipients=[],
    )

    with pytest.raises(ValueError, match="No recipients configured and no override provided"):
        send_email(
            config=config,
            recipients=None,
            subject="Test",
            body="Hello",
        )


@pytest.mark.os_agnostic
def test_send_email_raises_when_parameter_is_empty_list() -> None:
    """Explicit empty list parameter raises ValueError even with config recipients."""
    config = EmailConfig(
        smtphosts=["smtp.test.com:587"],
        from_address="sender@test.com",
        recipients=["config@test.com"],
    )

    with pytest.raises(ValueError, match="No recipients configured and no override provided"):
        send_email(
            config=config,
            recipients=[],
            subject="Test",
            body="Hello",
        )


# ======================== send_notification — recipients fallback ========================


@pytest.mark.os_agnostic
def test_send_notification_uses_config_recipients_when_parameter_is_none() -> None:
    """Notification falls back to config.recipients when parameter is None."""
    config = EmailConfig(
        smtphosts=["smtp.test.com:587"],
        from_address="alerts@test.com",
        recipients=["admin@test.com"],
    )

    transport = RecordingTransport()
    result = send_notification(
        config=config,
        subject="Alert",
        message="System notification",
        transport=transport,
    )

    assert result is True
    assert transport.recipients == ["admin@test.com"]


@pytest.mark.os_agnostic
def test_send_notification_raises_when_no_recipients_anywhere() -> None:
    """Notification with no recipients in config or parameter raises ValueError."""
    config = EmailConfig(
        smtphosts=["smtp.test.com:587"],
        from_address="alerts@test.com",
    )

    with pytest.raises(ValueError, match="No recipients configured and no override provided"):
        send_notification(
            config=config,
            subject="Alert",
            message="System notification",
        )


# ======================== send_email logging behavior ========================


@pytest.mark.os_agnostic
def test_send_email_logs_success_on_true_result(caplog: pytest.LogCaptureFixture) -> None:
    """When btx_send returns True, send_email logs at INFO level with success message."""
    import logging

    config = EmailConfig(
        smtphosts=["smtp.test.com:587"],
        from_address="sender@test.com",
    )

    with (
        patch("proxmox_srvbackup.adapters.email.transport.btx_send", return_value=True),
        caplog.at_level(logging.INFO),
    ):
        result = send_email(
            config=config,
            recipients="recipient@test.com",
            subject="Test",
            body="Hello",
        )

    assert result is True
    assert "Email sent successfully" in caplog.text
    assert "Email send returned failure" not in caplog.text


@pytest.mark.os_agnostic
def test_send_email_logs_warning_on_false_result(caplog: pytest.LogCaptureFixture) -> None:
    """When btx_send returns False, send_email logs at WARNING level."""
    import logging

    config = EmailConfig(
        smtphosts=["smtp.test.com:587"],
        from_address="sender@test.com",
    )

    with (
        patch("proxmox_srvbackup.adapters.email.transport.btx_send", return_value=False),
        caplog.at_level(logging.WARNING),
    ):
        result = send_email(
            config=config,
            recipients="recipient@test.com",
            subject="Test",
            body="Hello",
        )

    assert result is False
    assert "Email send returned failure" in caplog.text
    assert "Email sent successfully" not in caplog.text


# ======================== Real SMTP Integration ========================


@pytest.fixture
def smtp_config_from_env() -> EmailConfig:
    """Load SMTP configuration via lib_layered_config for integration tests."""
    from proxmox_srvbackup.adapters.config.loader import get_config
    from proxmox_srvbackup.adapters.email.sender import load_email_config_from_dict

    get_config.cache_clear()
    config = get_config()
    email_config = load_email_config_from_dict(config.as_dict())

    if not email_config.smtphosts or not email_config.from_address:
        pytest.skip("Email not configured (no smtp_hosts or from_address in layered config)")

    return email_config


@pytest.mark.local_only
@pytest.mark.integration
@pytest.mark.os_agnostic
def test_real_smtp_sends_email(smtp_config_from_env: EmailConfig) -> None:
    """Integration: send real email via configured SMTP server."""
    result = send_email(
        config=smtp_config_from_env,
        recipients=smtp_config_from_env.recipients,
        subject="Test Email from proxmox_srvbackup",
        body=(
            "This is a test email sent from the integration test suite."
            "\n\nIf you receive this, the email functionality is working correctly."
        ),
    )

    assert result is True


@pytest.mark.local_only
@pytest.mark.integration
@pytest.mark.os_agnostic
def test_real_smtp_sends_html_email(smtp_config_from_env: EmailConfig) -> None:
    """Integration: send HTML email via configured SMTP server."""
    result = send_email(
        config=smtp_config_from_env,
        recipients=smtp_config_from_env.recipients,
        subject="Test HTML Email from proxmox_srvbackup",
        body="This is the plain text version.",
        body_html="<html><body><h1>Test Email</h1><p>This is a <strong>HTML</strong> test email.</p></body></html>",
    )

    assert result is True


@pytest.mark.local_only
@pytest.mark.integration
@pytest.mark.os_agnostic
def test_real_smtp_sends_notification(smtp_config_from_env: EmailConfig) -> None:
    """Integration: send notification via configured SMTP server."""
    result = send_notification(
        config=smtp_config_from_env,
        recipients=smtp_config_from_env.recipients,
        subject="Test Notification from proxmox_srvbackup",
        message="This is a test notification.\n\nSystem: All tests passing!",
    )

    assert result is True


# ======================== validate_recipients function tests ========================


@pytest.mark.os_agnostic
def test_validate_recipients_accepts_none() -> None:
    """None recipients is a no-op (skips validation)."""
    from proxmox_srvbackup.adapters.email.validation import validate_recipients

    validate_recipients(None)  # Should not raise


@pytest.mark.os_agnostic
def test_validate_recipients_accepts_single_valid_string() -> None:
    """Single valid email address string is accepted."""
    from proxmox_srvbackup.adapters.email.validation import validate_recipients

    validate_recipients("valid@example.com")  # Should not raise


@pytest.mark.os_agnostic
def test_validate_recipients_accepts_valid_list() -> None:
    """List of valid email addresses is accepted."""
    from proxmox_srvbackup.adapters.email.validation import validate_recipients

    validate_recipients(["a@example.com", "b@example.com"])  # Should not raise


@pytest.mark.os_agnostic
def test_validate_recipients_accepts_empty_list() -> None:
    """Empty list is accepted (no recipients to validate)."""
    from proxmox_srvbackup.adapters.email.validation import validate_recipients

    validate_recipients([])  # Should not raise


@pytest.mark.os_agnostic
def test_validate_recipients_raises_on_invalid_single_string() -> None:
    """Invalid single email string raises InvalidRecipientError."""
    from proxmox_srvbackup.adapters.email.validation import validate_recipients
    from proxmox_srvbackup.domain.errors import InvalidRecipientError

    with pytest.raises(InvalidRecipientError, match="Invalid recipient"):
        validate_recipients("not-an-email")


@pytest.mark.os_agnostic
def test_validate_recipients_raises_on_invalid_in_list() -> None:
    """List with one invalid email raises InvalidRecipientError."""
    from proxmox_srvbackup.adapters.email.validation import validate_recipients
    from proxmox_srvbackup.domain.errors import InvalidRecipientError

    with pytest.raises(InvalidRecipientError, match="Invalid recipient"):
        validate_recipients(["valid@example.com", "invalid"])


@pytest.mark.os_agnostic
def test_validate_recipients_error_includes_invalid_address() -> None:
    """Error message includes the specific invalid address."""
    from proxmox_srvbackup.adapters.email.validation import validate_recipients
    from proxmox_srvbackup.domain.errors import InvalidRecipientError

    with pytest.raises(InvalidRecipientError, match="bad-address"):
        validate_recipients("bad-address")


@pytest.mark.os_agnostic
def test_starttls_verify_and_local_hostname_from_the_file_reach_the_transport() -> None:
    config = load_email_config_from_dict(
        {
            "email": {
                "smtp_hosts": ["smtp.test.com:587"],
                "from_address": "app@example.com",
                "starttls_verify": False,
                "local_hostname": "mail.example.com",
            }
        }
    )
    transport = RecordingTransport()

    send_email(config=config, recipients="ops@example.com", subject="s", transport=transport)

    assert transport.deliveries[0].local_hostname == "mail.example.com"
    assert transport.deliveries[0].starttls_verify is False


@pytest.mark.os_agnostic
def test_delivery_deadline_from_the_file_reaches_the_transport() -> None:
    config = load_email_config_from_dict(
        {"email": {"smtp_hosts": ["smtp.test.com:587"], "from_address": "app@example.com", "delivery_deadline": 90}}
    )
    transport = RecordingTransport()

    send_email(config=config, recipients="ops@example.com", subject="s", transport=transport)

    assert transport.deliveries[0].deadline == 90.0


@pytest.mark.os_agnostic
def test_recipient_max_count_from_the_file_refuses_a_larger_send_before_any_delivery() -> None:
    config = load_email_config_from_dict(
        {"email": {"smtp_hosts": ["smtp.test.com:587"], "from_address": "app@example.com", "recipient_max_count": 1}}
    )
    transport = RecordingTransport()

    with pytest.raises(ValueError, match=r"2 recipients, more than recipient_max_count \(1\)"):
        send_email(config=config, recipients=["a@example.com", "b@example.com"], subject="s", transport=transport)

    assert transport.attempted_hosts == []


@pytest.mark.os_agnostic
def test_attachments_max_count_from_the_file_refuses_a_larger_send_before_any_delivery(tmp_path: Path) -> None:
    first, second = tmp_path / "a.txt", tmp_path / "b.txt"
    first.write_text("a", encoding="utf-8")
    second.write_text("b", encoding="utf-8")
    config = load_email_config_from_dict(
        {
            "email": {
                "smtp_hosts": ["smtp.test.com:587"],
                "from_address": "app@example.com",
                "attachments": {"max_count": 1},
            }
        }
    )
    transport = RecordingTransport()

    with pytest.raises(ValueError, match=r"2 attachments, more than attachment_max_count \(1\)"):
        send_email(
            config=config, recipients="ops@example.com", subject="s", attachments=[first, second], transport=transport
        )

    assert transport.attempted_hosts == []


_SHIPPED_MAIL = (
    Path(__file__).parent.parent / "src" / "proxmox_srvbackup" / "adapters" / "config" / "defaultconfig.d"
) / "50-mail.toml"


@pytest.mark.os_agnostic
def test_the_shipped_defaults_verify_the_certificate_and_name_no_ehlo_host() -> None:
    shipped = rtoml.load(_SHIPPED_MAIL)["email"]
    assert shipped["starttls_verify"] is True
    assert shipped["local_hostname"] == ""


@pytest.mark.os_agnostic
def test_the_shipped_count_limits_and_deadline_load_as_the_library_defaults() -> None:
    shipped = rtoml.load(_SHIPPED_MAIL)
    # The keys are written out, so a reader of the shipped file sees them: the premise.
    assert "recipient_max_count" in shipped["email"]
    assert "delivery_deadline" in shipped["email"]
    assert "max_count" in shipped["email"]["attachments"]
    loaded = load_email_config_from_dict(shipped)
    library = ConfMail()

    assert loaded.recipient_max_count == library.recipient_max_count
    assert loaded.attachment_max_count == library.attachment_max_count
    assert loaded.smtp_delivery_deadline is library.smtp_delivery_deadline is None
