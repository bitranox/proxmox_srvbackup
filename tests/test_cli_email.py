"""CLI email stories: send-email, send-notification, SMTP overrides, credential overrides."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from proxmox_srvbackup.adapters import cli as cli_mod

if TYPE_CHECKING:
    from collections.abc import Callable

    from click.testing import CliRunner, Result

    from conftest import EmailCliContext

# ======================== Email Command Tests ========================


@pytest.mark.os_agnostic
def test_when_send_email_is_invoked_without_smtp_hosts_it_fails(
    cli_runner: CliRunner,
    email_cli_context: Callable[[dict[str, Any]], EmailCliContext],
) -> None:
    """When SMTP hosts are not configured, send-email should exit with CONFIG_ERROR (78)."""
    ctx = email_cli_context({})

    result: Result = cli_runner.invoke(
        cli_mod.cli,
        [
            "send-email",
            "--to",
            "recipient@test.com",
            "--subject",
            "Test",
            "--body",
            "Hello",
        ],
        obj=ctx.factory,
    )

    assert result.exit_code == 78
    assert "No SMTP hosts configured" in result.output


@pytest.mark.os_agnostic
def test_when_send_email_is_invoked_with_valid_config_it_sends(
    cli_runner: CliRunner,
    email_cli_context: Callable[[dict[str, Any]], EmailCliContext],
) -> None:
    """When SMTP is configured, send-email should successfully send."""
    ctx = email_cli_context(
        {
            "smtp_hosts": ["smtp.test.com:587"],
            "from_address": "sender@test.com",
        }
    )

    result: Result = cli_runner.invoke(
        cli_mod.cli,
        [
            "send-email",
            "--to",
            "recipient@test.com",
            "--subject",
            "Test Subject",
            "--body",
            "Test body",
        ],
        obj=ctx.factory,
    )

    assert result.exit_code == 0
    assert "Email sent successfully" in result.output
    assert len(ctx.spy.sent_emails) == 1
    assert ctx.spy.sent_emails[0].subject == "Test Subject"
    assert ctx.spy.sent_emails[0].recipients == ["recipient@test.com"]


@pytest.mark.os_agnostic
def test_when_send_email_receives_multiple_recipients_it_accepts_them(
    cli_runner: CliRunner,
    email_cli_context: Callable[[dict[str, Any]], EmailCliContext],
) -> None:
    """When multiple --to flags are provided, send-email should accept them."""
    ctx = email_cli_context(
        {
            "smtp_hosts": ["smtp.test.com:587"],
            "from_address": "sender@test.com",
        }
    )

    result: Result = cli_runner.invoke(
        cli_mod.cli,
        [
            "send-email",
            "--to",
            "user1@test.com",
            "--to",
            "user2@test.com",
            "--subject",
            "Test",
            "--body",
            "Hello",
        ],
        obj=ctx.factory,
    )

    assert result.exit_code == 0
    assert ctx.spy.sent_emails[0].recipients == ["user1@test.com", "user2@test.com"]


@pytest.mark.os_agnostic
def test_when_send_email_includes_html_body_it_sends(
    cli_runner: CliRunner,
    email_cli_context: Callable[[dict[str, Any]], EmailCliContext],
) -> None:
    """When HTML body is provided, send-email should include it."""
    ctx = email_cli_context(
        {
            "smtp_hosts": ["smtp.test.com:587"],
            "from_address": "sender@test.com",
        }
    )

    result: Result = cli_runner.invoke(
        cli_mod.cli,
        [
            "send-email",
            "--to",
            "recipient@test.com",
            "--subject",
            "Test",
            "--body",
            "Plain text",
            "--body-html",
            "<h1>HTML</h1>",
        ],
        obj=ctx.factory,
    )

    assert result.exit_code == 0
    assert ctx.spy.sent_emails[0].body_html == "<h1>HTML</h1>"


@pytest.mark.os_agnostic
def test_when_send_email_has_attachments_it_sends(
    cli_runner: CliRunner,
    tmp_path: Any,
    email_cli_context: Callable[[dict[str, Any]], EmailCliContext],
) -> None:
    """When attachments are provided, send-email should include them."""
    from pathlib import Path

    attachment = tmp_path / "test.txt"
    attachment.write_text("Test content")

    ctx = email_cli_context(
        {
            "smtp_hosts": ["smtp.test.com:587"],
            "from_address": "sender@test.com",
        }
    )

    result: Result = cli_runner.invoke(
        cli_mod.cli,
        [
            "send-email",
            "--to",
            "recipient@test.com",
            "--subject",
            "Test",
            "--body",
            "See attachment",
            "--attachment",
            str(attachment),
        ],
        obj=ctx.factory,
    )

    assert result.exit_code == 0
    assert ctx.spy.sent_emails[0].attachments == [Path(attachment)]


@pytest.mark.os_agnostic
def test_when_send_email_smtp_fails_it_reports_error(
    cli_runner: CliRunner,
    email_cli_context: Callable[[dict[str, Any]], EmailCliContext],
) -> None:
    """When SMTP returns failure, send-email should show SMTP_FAILURE (69) error."""
    ctx = email_cli_context(
        {
            "smtp_hosts": ["smtp.test.com:587"],
            "from_address": "sender@test.com",
        }
    )
    ctx.spy.should_fail = True

    result: Result = cli_runner.invoke(
        cli_mod.cli,
        [
            "send-email",
            "--to",
            "recipient@test.com",
            "--subject",
            "Test",
            "--body",
            "Hello",
        ],
        obj=ctx.factory,
    )

    assert result.exit_code == 69
    assert "failed" in result.output.lower()
    assert "SMTP delivery failed" not in result.stderr
    assert "Failed to send email" not in result.stderr


@pytest.mark.os_agnostic
def test_when_send_notification_is_invoked_without_smtp_hosts_it_fails(
    cli_runner: CliRunner,
    email_cli_context: Callable[[dict[str, Any]], EmailCliContext],
) -> None:
    """When SMTP hosts are not configured, send-notification should exit with CONFIG_ERROR (78)."""
    ctx = email_cli_context({})

    result: Result = cli_runner.invoke(
        cli_mod.cli,
        [
            "send-notification",
            "--to",
            "admin@test.com",
            "--subject",
            "Alert",
            "--message",
            "System notification",
        ],
        obj=ctx.factory,
    )

    assert result.exit_code == 78
    assert "No SMTP hosts configured" in result.output


@pytest.mark.os_agnostic
def test_when_send_notification_is_invoked_with_valid_config_it_sends(
    cli_runner: CliRunner,
    email_cli_context: Callable[[dict[str, Any]], EmailCliContext],
) -> None:
    """When SMTP is configured, send-notification should successfully send."""
    ctx = email_cli_context(
        {
            "smtp_hosts": ["smtp.test.com:587"],
            "from_address": "alerts@test.com",
        }
    )

    result: Result = cli_runner.invoke(
        cli_mod.cli,
        [
            "send-notification",
            "--to",
            "admin@test.com",
            "--subject",
            "Alert",
            "--message",
            "System notification",
        ],
        obj=ctx.factory,
    )

    assert result.exit_code == 0
    assert "Notification sent successfully" in result.output
    assert len(ctx.spy.sent_notifications) == 1
    assert ctx.spy.sent_notifications[0].subject == "Alert"
    assert ctx.spy.sent_notifications[0].message == "System notification"


@pytest.mark.os_agnostic
def test_when_send_notification_receives_multiple_recipients_it_accepts_them(
    cli_runner: CliRunner,
    email_cli_context: Callable[[dict[str, Any]], EmailCliContext],
) -> None:
    """When multiple --to flags are provided, send-notification should accept them."""
    ctx = email_cli_context(
        {
            "smtp_hosts": ["smtp.test.com:587"],
            "from_address": "alerts@test.com",
        }
    )

    result: Result = cli_runner.invoke(
        cli_mod.cli,
        [
            "send-notification",
            "--to",
            "admin1@test.com",
            "--to",
            "admin2@test.com",
            "--subject",
            "Alert",
            "--message",
            "System notification",
        ],
        obj=ctx.factory,
    )

    assert result.exit_code == 0
    assert ctx.spy.sent_notifications[0].recipients == ["admin1@test.com", "admin2@test.com"]


@pytest.mark.os_agnostic
def test_when_send_notification_smtp_fails_it_reports_error(
    cli_runner: CliRunner,
    email_cli_context: Callable[[dict[str, Any]], EmailCliContext],
) -> None:
    """When SMTP returns failure, send-notification should show SMTP_FAILURE (69) error."""
    ctx = email_cli_context(
        {
            "smtp_hosts": ["smtp.test.com:587"],
            "from_address": "alerts@test.com",
        }
    )
    ctx.spy.should_fail = True

    result: Result = cli_runner.invoke(
        cli_mod.cli,
        [
            "send-notification",
            "--to",
            "admin@test.com",
            "--subject",
            "Alert",
            "--message",
            "System notification",
        ],
        obj=ctx.factory,
    )

    assert result.exit_code == 69
    assert "failed" in result.output.lower()
    assert "SMTP delivery failed" not in result.stderr
    assert "Failed to send email" not in result.stderr


# ======================== SMTP Config Override Tests ========================


@pytest.mark.os_agnostic
def test_when_send_email_receives_smtp_host_override_it_uses_it(
    cli_runner: CliRunner,
    email_cli_context: Callable[[dict[str, Any]], EmailCliContext],
) -> None:
    """When --smtp-host is provided, send-email should use the override instead of config value."""
    ctx = email_cli_context(
        {
            "smtp_hosts": ["smtp.config.com:587"],
            "from_address": "sender@test.com",
        }
    )

    result: Result = cli_runner.invoke(
        cli_mod.cli,
        [
            "send-email",
            "--to",
            "recipient@test.com",
            "--subject",
            "Test",
            "--body",
            "Hello",
            "--smtp-host",
            "smtp.override.com:465",
        ],
        obj=ctx.factory,
    )

    assert result.exit_code == 0
    assert ctx.spy.sent_emails[0].config.smtphosts == ["smtp.override.com:465"]


@pytest.mark.os_agnostic
def test_when_send_email_receives_timeout_override_it_uses_it(
    cli_runner: CliRunner,
    email_cli_context: Callable[[dict[str, Any]], EmailCliContext],
) -> None:
    """When --timeout is provided, send-email should use the overridden timeout."""
    ctx = email_cli_context(
        {
            "smtp_hosts": ["smtp.test.com:587"],
            "from_address": "sender@test.com",
        }
    )

    result: Result = cli_runner.invoke(
        cli_mod.cli,
        [
            "send-email",
            "--to",
            "recipient@test.com",
            "--subject",
            "Test",
            "--body",
            "Hello",
            "--timeout",
            "60",
        ],
        obj=ctx.factory,
    )

    assert result.exit_code == 0
    assert ctx.spy.sent_emails[0].config.smtp_timeout == 60.0


@pytest.mark.os_agnostic
def test_when_send_email_receives_no_use_starttls_override_it_applies_it(
    cli_runner: CliRunner,
    email_cli_context: Callable[[dict[str, Any]], EmailCliContext],
) -> None:
    """When --no-use-starttls is provided, send-email should disable starttls in config."""
    ctx = email_cli_context(
        {
            "smtp_hosts": ["smtp.test.com:587"],
            "from_address": "sender@test.com",
        }
    )

    result: Result = cli_runner.invoke(
        cli_mod.cli,
        [
            "send-email",
            "--to",
            "recipient@test.com",
            "--subject",
            "Test",
            "--body",
            "Hello",
            "--no-use-starttls",
        ],
        obj=ctx.factory,
    )

    assert result.exit_code == 0
    assert ctx.spy.sent_emails[0].config.smtp_use_starttls is False


@pytest.mark.os_agnostic
def test_when_send_email_receives_credential_overrides_it_uses_them(
    cli_runner: CliRunner,
    email_cli_context: Callable[[dict[str, Any]], EmailCliContext],
) -> None:
    """When --smtp-username and --smtp-password are provided, send-email should use them."""
    ctx = email_cli_context(
        {
            "smtp_hosts": ["smtp.test.com:587"],
            "from_address": "sender@test.com",
        }
    )

    result: Result = cli_runner.invoke(
        cli_mod.cli,
        [
            "send-email",
            "--to",
            "recipient@test.com",
            "--subject",
            "Test",
            "--body",
            "Hello",
            "--smtp-username",
            "myuser",
            "--smtp-password",
            "mypass",
        ],
        obj=ctx.factory,
    )

    assert result.exit_code == 0
    assert ctx.spy.sent_emails[0].config.smtp_username == "myuser"
    password = ctx.spy.sent_emails[0].config.smtp_password
    assert password is not None
    assert password.get_secret_value() == "mypass"


@pytest.mark.os_agnostic
def test_when_send_notification_receives_from_override_it_uses_it(
    cli_runner: CliRunner,
    email_cli_context: Callable[[dict[str, Any]], EmailCliContext],
) -> None:
    """When --from is provided, send-notification should use the override sender."""
    ctx = email_cli_context(
        {
            "smtp_hosts": ["smtp.test.com:587"],
            "from_address": "default@test.com",
        }
    )

    result: Result = cli_runner.invoke(
        cli_mod.cli,
        [
            "send-notification",
            "--to",
            "admin@test.com",
            "--subject",
            "Alert",
            "--message",
            "System notification",
            "--from",
            "override@test.com",
        ],
        obj=ctx.factory,
    )

    assert result.exit_code == 0
    assert ctx.spy.sent_notifications[0].from_address == "override@test.com"


@pytest.mark.os_agnostic
def test_when_send_notification_receives_smtp_host_override_it_uses_it(
    cli_runner: CliRunner,
    email_cli_context: Callable[[dict[str, Any]], EmailCliContext],
) -> None:
    """When --smtp-host is provided, send-notification should use the override host."""
    ctx = email_cli_context(
        {
            "smtp_hosts": ["smtp.config.com:587"],
            "from_address": "sender@test.com",
        }
    )

    result: Result = cli_runner.invoke(
        cli_mod.cli,
        [
            "send-notification",
            "--to",
            "admin@test.com",
            "--subject",
            "Alert",
            "--message",
            "System notification",
            "--smtp-host",
            "smtp.override.com:465",
        ],
        obj=ctx.factory,
    )

    assert result.exit_code == 0
    assert ctx.spy.sent_notifications[0].config.smtphosts == ["smtp.override.com:465"]


@pytest.mark.os_agnostic
@pytest.mark.parametrize("flag", ["--raise-on-missing-attachments", "--no-raise-on-missing-attachments"])
def test_when_send_notification_receives_a_missing_attachments_flag_it_refuses_the_option(
    cli_runner: CliRunner,
    email_cli_context: Callable[[dict[str, Any]], EmailCliContext],
    flag: str,
) -> None:
    """send-notification takes no attachments, so it offers no missing-attachment switch."""
    ctx = email_cli_context({"smtp_hosts": ["smtp.test.com:587"], "from_address": "alerts@test.com"})

    result: Result = cli_runner.invoke(
        cli_mod.cli,
        ["send-notification", "--to", "admin@test.com", "--subject", "Alert", "--message", "Hi", flag],
        obj=ctx.factory,
    )

    assert result.exit_code == 2
    assert "No such option" in result.output
    assert ctx.spy.sent_notifications == []


@pytest.mark.os_agnostic
def test_when_send_email_receives_no_raise_on_missing_attachments_it_overrides_the_config(
    cli_runner: CliRunner,
    email_cli_context: Callable[[dict[str, Any]], EmailCliContext],
) -> None:
    """send-email keeps the switch: --no-raise-on-missing-attachments reaches the delivery config."""
    ctx = email_cli_context({"smtp_hosts": ["smtp.test.com:587"], "from_address": "sender@test.com"})

    result: Result = cli_runner.invoke(
        cli_mod.cli,
        ["send-email", "--to", "r@test.com", "--subject", "S", "--body", "B", "--no-raise-on-missing-attachments"],
        obj=ctx.factory,
    )

    assert result.exit_code == 0
    assert ctx.spy.sent_emails[0].config.raise_on_missing_attachments is False


# ======================== Attachment path validation ========================


@pytest.mark.os_agnostic
def test_when_send_email_attachment_missing_with_raise_flag_it_fails(
    cli_runner: CliRunner,
    config_cli_context: Callable[[dict[str, Any]], Callable[[], Any]],
    tmp_path: Any,
) -> None:
    """Missing attachment with default raise behavior should fail with FILE_NOT_FOUND.

    This test uses the production adapter to verify actual file validation behavior.
    The memory adapter doesn't validate file paths, so we use smtplib mock here.
    """
    from unittest.mock import patch

    factory = config_cli_context(
        {
            "email": {
                "smtp_hosts": ["smtp.test.com:587"],
                "from_address": "sender@test.com",
                # Whitelist tmp_path for attachment security
                # (macOS tmp_path is under /var which is blocked by default)
                "attachments": {
                    "allowed_directories": [str(tmp_path)],
                },
            }
        }
    )

    nonexistent_file = str(tmp_path / "nonexistent_attachment.txt")

    with patch("smtplib.SMTP"):
        result: Result = cli_runner.invoke(
            cli_mod.cli,
            [
                "send-email",
                "--to",
                "recipient@test.com",
                "--subject",
                "Test",
                "--body",
                "Hello",
                "--attachment",
                nonexistent_file,
            ],
            obj=factory,
        )

    # Default: raise_on_missing_attachments=True, so FileNotFoundError is raised
    assert result.exit_code != 0
    # Could be FILE_NOT_FOUND (66) or the error message in output
    assert "not found" in result.output.lower() or result.exit_code == 66


@pytest.mark.os_agnostic
def test_when_send_email_attachment_path_accepted_by_click(
    cli_runner: CliRunner,
    config_cli_context: Callable[[dict[str, Any]], Callable[[], Any]],
    tmp_path: Any,
) -> None:
    """Click accepts nonexistent attachment paths (validation delegated to app).

    This test uses the production adapter to verify actual file validation behavior.
    """
    from unittest.mock import patch

    factory = config_cli_context(
        {
            "email": {
                "smtp_hosts": ["smtp.test.com:587"],
                "from_address": "sender@test.com",
                # Whitelist tmp_path for attachment security
                # (macOS tmp_path is under /var which is blocked by default)
                "attachments": {
                    "allowed_directories": [str(tmp_path)],
                },
            }
        }
    )

    nonexistent_file = str(tmp_path / "nonexistent_attachment.txt")

    with patch("smtplib.SMTP"):
        result: Result = cli_runner.invoke(
            cli_mod.cli,
            [
                "send-email",
                "--to",
                "recipient@test.com",
                "--subject",
                "Test",
                "--body",
                "Hello",
                "--attachment",
                nonexistent_file,
            ],
            obj=factory,
        )

    # Click doesn't reject with "Path ... does not exist"
    assert "does not exist" not in result.output
    # Error comes from application layer
    assert result.exit_code != 0
    assert "Attachment" in result.output or "not found" in result.output.lower()


# ======================== CLI Override Validation Tests ========================


@pytest.mark.os_agnostic
def test_when_send_email_receives_negative_timeout_it_exits_invalid_argument(
    cli_runner: CliRunner,
    email_cli_context: Callable[[dict[str, Any]], EmailCliContext],
) -> None:
    """When --timeout is negative, send-email should exit with INVALID_ARGUMENT (22)."""
    ctx = email_cli_context(
        {
            "smtp_hosts": ["smtp.test.com:587"],
            "from_address": "sender@test.com",
        }
    )

    result: Result = cli_runner.invoke(
        cli_mod.cli,
        [
            "send-email",
            "--to",
            "recipient@test.com",
            "--subject",
            "Test",
            "--body",
            "Hello",
            "--timeout",
            "-5",
        ],
        obj=ctx.factory,
    )

    assert result.exit_code == 22
    assert "Invalid option value" in result.output or "timeout must be positive" in result.output


@pytest.mark.os_agnostic
def test_when_send_email_receives_invalid_smtp_host_it_exits_invalid_argument(
    cli_runner: CliRunner,
    email_cli_context: Callable[[dict[str, Any]], EmailCliContext],
) -> None:
    """When --smtp-host has invalid format, send-email should exit with INVALID_ARGUMENT (22)."""
    ctx = email_cli_context(
        {
            "smtp_hosts": ["smtp.test.com:587"],
            "from_address": "sender@test.com",
        }
    )

    result: Result = cli_runner.invoke(
        cli_mod.cli,
        [
            "send-email",
            "--to",
            "recipient@test.com",
            "--subject",
            "Test",
            "--body",
            "Hello",
            "--smtp-host",
            "not-a-valid-host:99999",
        ],
        obj=ctx.factory,
    )

    assert result.exit_code == 22
    assert "Invalid option value" in result.output


@pytest.mark.os_agnostic
def test_when_send_email_receives_invalid_runtime_recipient_it_fails(
    cli_runner: CliRunner,
    email_cli_context: Callable[[dict[str, Any]], EmailCliContext],
) -> None:
    """When --to has invalid email format, send-email should fail with INVALID_ARGUMENT (22)."""
    ctx = email_cli_context(
        {
            "smtp_hosts": ["smtp.test.com:587"],
            "from_address": "sender@test.com",
        }
    )

    result: Result = cli_runner.invoke(
        cli_mod.cli,
        [
            "send-email",
            "--to",
            "not-an-email",
            "--subject",
            "Test",
            "--body",
            "Hello",
        ],
        obj=ctx.factory,
    )

    assert result.exit_code == 22
    assert "Invalid" in result.output


@pytest.mark.os_agnostic
def test_when_send_notification_receives_negative_timeout_it_exits_invalid_argument(
    cli_runner: CliRunner,
    email_cli_context: Callable[[dict[str, Any]], EmailCliContext],
) -> None:
    """When --timeout is negative, send-notification should exit with INVALID_ARGUMENT (22)."""
    ctx = email_cli_context(
        {
            "smtp_hosts": ["smtp.test.com:587"],
            "from_address": "sender@test.com",
        }
    )

    result: Result = cli_runner.invoke(
        cli_mod.cli,
        [
            "send-notification",
            "--to",
            "recipient@test.com",
            "--subject",
            "Alert",
            "--message",
            "Hello",
            "--timeout",
            "-5",
        ],
        obj=ctx.factory,
    )

    assert result.exit_code == 22
    assert "Invalid option value" in result.output or "timeout must be positive" in result.output
