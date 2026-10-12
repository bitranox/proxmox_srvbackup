"""Shared utilities for email CLI commands.

Contains configuration loading, error handling, and option decorators
shared between send-email and send-notification commands.
"""

from __future__ import annotations

import functools
import logging
import os
from typing import TYPE_CHECKING, Any, NoReturn

from btx_lib_mail import AttachmentSecurityError, SecretSafeModel
from pydantic import ConfigDict, SecretStr, ValidationError

from proxmox_srvbackup import __init__conf__
from proxmox_srvbackup.adapters.email.config import describe_validation_error
from proxmox_srvbackup.adapters.email.sender import EmailConfig
from proxmox_srvbackup.domain.errors import ConfigurationError, DeliveryError

from ... import safe_console
from ...exit_codes import ExitCode
from ...typed_click import get_current_context, option

if TYPE_CHECKING:
    from collections.abc import Callable

    from lib_layered_config import Config

    from proxmox_srvbackup.application.ports import LoadEmailConfigFromDict

logger = logging.getLogger(__name__)


class EmailConfigOverrides(SecretSafeModel):
    """The EmailConfig fields the command line overrides; ``None`` means the option was not given.

    Each field carries EmailConfig's own name, so a field EmailConfig renames is refused here
    instead of being passed along unnoticed. The password stays a ``SecretStr`` from the moment
    the command line hands it over, and a validation error never carries its value, not even in
    ``errors()`` or ``json()``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    credential_fields = frozenset({"smtp_password"})

    smtphosts: tuple[str, ...] | None = None
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_use_starttls: bool | None = None
    smtp_timeout: float | None = None
    raise_on_missing_attachments: bool | None = None
    raise_on_invalid_recipient: bool | None = None

    @classmethod
    def from_cli_options(
        cls,
        *,
        smtp_hosts: tuple[str, ...] = (),
        smtp_username: str | None = None,
        smtp_password: str | None = None,
        use_starttls: bool | None = None,
        timeout: float | None = None,
        raise_on_missing_attachments: bool | None = None,
        raise_on_invalid_recipient: bool | None = None,
    ) -> EmailConfigOverrides:
        """Build the overrides from the values Click hands a command.

        Click reports an option that was not given as ``None``, and a ``multiple=True`` option
        that was not given as an empty tuple; both become ``None`` here.

        Examples:
            >>> EmailConfigOverrides.from_cli_options(smtp_hosts=(), timeout=5.0).model_dump(exclude_none=True)
            {'smtp_timeout': 5.0}
        """
        return cls(
            smtphosts=smtp_hosts or None,
            smtp_username=smtp_username,
            smtp_password=None if smtp_password is None else SecretStr(smtp_password),
            smtp_use_starttls=use_starttls,
            smtp_timeout=timeout,
            raise_on_missing_attachments=raise_on_missing_attachments,
            raise_on_invalid_recipient=raise_on_invalid_recipient,
        )


def apply_validated_overrides(base_config: EmailConfig, overrides: EmailConfigOverrides) -> EmailConfig:
    """Apply overrides with full Pydantic validation.

    Uses model_validate() with a merged mapping instead of model_copy(update=...)
    to ensure EmailConfig's validators run on all overridden values.

    Args:
        base_config: Base EmailConfig to merge overrides into.
        overrides: The options given on the command line.

    Returns:
        ``base_config`` itself when no option was given, else a new EmailConfig with the
        overrides applied and validated.

    Raises:
        ValidationError: When overrides contain invalid values.
    """
    given = overrides.model_dump(exclude_none=True)
    if not given:
        return base_config
    return EmailConfig.model_validate({**base_config.model_dump(), **given})


def smtp_config_options(func: Callable[..., Any]) -> Callable[..., Any]:
    """Apply shared SMTP configuration override options to a Click command.

    Adds CLI flags for the SMTP connection and delivery settings (hosts, credentials,
    STARTTLS, timeout, ``raise_on_invalid_recipient``). ``send-email`` adds its own
    ``--raise-on-missing-attachments`` switch, since only it takes attachments.
    ``starttls_verify``, ``local_hostname``, ``delivery_deadline``, ``recipient_max_count``
    and the attachment settings have no flag; set them with ``--set email.<key>=...``.
    """
    options = [
        option(
            "--smtp-host",
            "smtp_hosts",
            multiple=True,
            default=(),
            help="Override SMTP host (can specify multiple; format host:port)",
        ),
        option("--smtp-username", default=None, help="Override SMTP authentication username"),
        option("--smtp-password", default=None, help="Override SMTP authentication password"),
        option("--use-starttls/--no-use-starttls", default=None, help="Override STARTTLS setting"),
        option("--timeout", "timeout", type=float, default=None, help="Override socket timeout in seconds"),
        option(
            "--raise-on-invalid-recipient/--no-raise-on-invalid-recipient",
            default=None,
            help="Override invalid recipient handling",
        ),
    ]
    return functools.reduce(lambda f, opt: opt(f), reversed(options), func)


def load_and_validate_email_config(config: Config, loader: LoadEmailConfigFromDict) -> EmailConfig:
    """Extract and validate email config from the provided Config object.

    Args:
        config: Already-loaded layered configuration object.
        loader: Function to load EmailConfig from dict.

    Returns:
        EmailConfig with validated SMTP configuration.

    Raises:
        click.exceptions.Exit: When the ``[email]`` section is invalid, one ``Error:`` line per
            problem, or when SMTP hosts are not configured (exit code 78 / CONFIG_ERROR).
    """
    try:
        email_config = loader(config.as_dict())
    except ValidationError as exc:
        _refuse_email_config(exc, "Invalid configuration", exit_code=ExitCode.CONFIG_ERROR)

    if not email_config.smtphosts:
        logger.error("No SMTP hosts configured")
        safe_console.echo(
            "\nError: No SMTP hosts configured. Please configure email.smtp_hosts in your config file.", err=True
        )
        safe_console.echo(f"See: {__init__conf__.shell_command} config-deploy --target user", err=True)
        get_current_context().exit(ExitCode.CONFIG_ERROR)

    return email_config


def execute_with_email_error_handling(
    *,
    operation: Callable[[], bool],
    recipients: list[str] | None,
    message_type: str,
    catches_file_not_found: bool = False,
) -> None:
    """Execute an email operation with unified error handling.

    Args:
        operation: Zero-arg callable returning True on success.
        recipients: Recipients for logging context.
        message_type: "Email" or "Notification" for display messages.
        catches_file_not_found: When True, catches FileNotFoundError
            (needed for send-email with attachments).

    Raises:
        click.exceptions.Exit: On any error (unless DEVELOPMENT_MODE is set).
        Exception: Re-raised in development mode for debugging.

    Exception Priority Order:
        Exceptions are caught in specificity order (most specific first):

        1. ConfigurationError -> CONFIG_ERROR (78): Missing/invalid config
        2. ValueError -> INVALID_ARGUMENT (22): Invalid parameters or email format
        3. FileNotFoundError -> FILE_NOT_FOUND (2): Missing attachment (if enabled)
        4. AttachmentSecurityError -> ATTACHMENT_REFUSED (77): An attachment btx_lib_mail's
           security checks refuse (blocked extension or directory, symlink, size, ...)
        5. DeliveryError/RuntimeError -> SMTP_FAILURE (69): SMTP transport failures
        6. Exception (catch-all) -> GENERAL_ERROR (1): Unexpected errors with traceback

        This ordering ensures specific exceptions aren't caught by broader handlers.
        When adding new exception types, insert them before the catch-all Exception handler.

    Development Mode:
        Set the DEVELOPMENT_MODE environment variable to any truthy value to
        re-raise unexpected exceptions instead of catching them. This surfaces
        bugs with full tracebacks during development.
    """
    try:
        result = operation()
    except ConfigurationError as exc:
        _handle_send_error(
            exc,
            f"{message_type} configuration error",
            "Configuration error",
            exit_code=ExitCode.CONFIG_ERROR,
        )
    except ValueError as exc:
        _handle_send_error(
            exc,
            f"Invalid {message_type.lower()} parameters",
            f"Invalid {message_type.lower()} parameters",
            exit_code=ExitCode.INVALID_ARGUMENT,
        )
    except FileNotFoundError as exc:
        if not catches_file_not_found:
            raise
        _handle_send_error(
            exc,
            "Attachment file not found",
            "Attachment file not found",
            exit_code=ExitCode.FILE_NOT_FOUND,
        )
    except AttachmentSecurityError as exc:
        _refuse_attachment(exc)
    except (DeliveryError, RuntimeError) as exc:
        _handle_send_error(
            exc,
            "SMTP delivery failed",
            "Failed to send email",
            exit_code=ExitCode.SMTP_FAILURE,
        )
    except Exception as exc:
        # In development mode, re-raise to surface bugs with full traceback
        if os.environ.get("DEVELOPMENT_MODE"):
            raise
        _handle_send_error(
            exc,
            f"Unexpected error sending {message_type.lower()}",
            "Unexpected error",
            exit_code=ExitCode.GENERAL_ERROR,
            log_traceback=True,
        )
    else:
        # Outside the try on purpose: a failed send exits through click's Exit, which is a
        # RuntimeError, so inside the try the DeliveryError/RuntimeError branch would catch it
        # and report the same failure a second time as "SMTP delivery failed".
        _handle_send_result(result, recipients, message_type)


def handle_validation_error(exc: ValidationError) -> NoReturn:
    """Refuse an invalid command-line override, one ``Error:`` line per problem.

    Args:
        exc: The validation error.

    Raises:
        click.exceptions.Exit: Always raised, with the INVALID_ARGUMENT exit code.
    """
    _refuse_email_config(exc, "Invalid option value", exit_code=ExitCode.INVALID_ARGUMENT)


def _refuse_email_config(exc: ValidationError, heading: str, *, exit_code: ExitCode) -> NoReturn:
    """Log and print an EmailConfig validation error as one line per problem, then exit.

    pydantic's own report spans several lines per problem and ends each with a documentation
    URL; :func:`describe_validation_error` gives ``email.<key>: <reason>`` without the input,
    which can be the SMTP password.

    Args:
        exc: The validation error.
        heading: What was invalid, e.g. "Invalid configuration" for the file.
        exit_code: The code to exit with.

    Raises:
        click.exceptions.Exit: Always raised, with ``exit_code``.
    """
    problems = describe_validation_error(exc)
    logger.error(heading, extra={"problems": problems, "error_type": type(exc).__name__})
    for problem in problems:
        safe_console.echo(f"Error: {heading}: {problem}", err=True)
    get_current_context().exit(exit_code)


def _refuse_attachment(exc: AttachmentSecurityError) -> NoReturn:
    """Report an attachment btx_lib_mail refused on security grounds, then exit 77.

    The refusal is policy working as configured, not a crash, so no traceback is logged. The
    user sees the library's reason, which names the violation and the resolved path; it never
    carries a credential.

    Args:
        exc: The refusal btx_lib_mail raised.

    Raises:
        click.exceptions.Exit: Always raised, with the ATTACHMENT_REFUSED exit code.
    """
    logger.error(
        "Attachment refused by security policy",
        extra={"reason": exc.reason, "violation_type": exc.violation_type.value},
    )
    safe_console.echo(f"\nError: Attachment refused by security policy - {exc.reason}", err=True)
    get_current_context().exit(ExitCode.ATTACHMENT_REFUSED)


def _handle_send_result(result: bool, recipients: list[str] | None, message_type: str) -> None:
    """Handle the result of a send operation.

    Args:
        result: True if send succeeded.
        recipients: Email recipients, or None when config defaults were used.
        message_type: "Email" or "Notification" for display.

    Raises:
        click.exceptions.Exit: If the send failed.
    """
    if result:
        safe_console.echo(f"\n{message_type} sent successfully!")
        logger.info("%s sent via CLI", message_type, extra={"recipients": recipients})
    else:
        safe_console.echo(f"\n{message_type} sending failed.", err=True)
        get_current_context().exit(ExitCode.SMTP_FAILURE)


def _handle_send_error(
    exc: Exception,
    log_message: str,
    user_message: str,
    *,
    exit_code: ExitCode = ExitCode.GENERAL_ERROR,
    log_traceback: bool = False,
) -> None:
    """Handle errors during send operations.

    Args:
        exc: The exception that occurred.
        log_message: Message for the logger.
        user_message: Message prefix for user display.
        exit_code: Exit code to use (default: GENERAL_ERROR).
        log_traceback: Whether to include traceback in logs.

    Raises:
        click.exceptions.Exit: Always raised, with the given exit code. Commands exit through
            click's context, never a bare ``SystemExit``, which ``main()`` would print as
            ``SystemExit: N``.
    """
    logger.error(
        log_message,
        extra={"error": str(exc), "error_type": type(exc).__name__},
        exc_info=log_traceback,
    )
    safe_console.echo(f"\nError: {user_message} - {exc}", err=True)
    get_current_context().exit(exit_code)


__all__ = [
    "EmailConfigOverrides",
    "apply_validated_overrides",
    "execute_with_email_error_handling",
    "handle_validation_error",
    "load_and_validate_email_config",
    "smtp_config_options",
]
