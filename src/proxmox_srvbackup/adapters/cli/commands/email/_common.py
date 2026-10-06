"""Shared utilities for email CLI commands.

Contains configuration loading, error handling, and option decorators
shared between send-email and send-notification commands.
"""

from __future__ import annotations

import functools
import logging
import os
from typing import TYPE_CHECKING, Any, NoReturn, cast

import rich_click as click
from pydantic import ValidationError

from proxmox_srvbackup import __init__conf__
from proxmox_srvbackup.adapters.email.config import describe_validation_error
from proxmox_srvbackup.adapters.email.sender import EmailConfig
from proxmox_srvbackup.domain.errors import ConfigurationError, DeliveryError

from ...exit_codes import ExitCode
from ...typed_click import get_current_context, option

if TYPE_CHECKING:
    from collections.abc import Callable

    from lib_layered_config import Config

    from proxmox_srvbackup.application.ports import LoadEmailConfigFromDict

logger = logging.getLogger(__name__)


def filter_sentinels(**kwargs: Any) -> dict[str, Any]:
    """Filter out None and empty tuple sentinels, converting tuples to lists.

    Used to prepare CLI option overrides for ``_apply_validated_overrides()``.
    Removes None values (unset options) and empty tuples (unset multiple options),
    and converts non-empty tuples to lists for Pydantic compatibility.

    Args:
        **kwargs: Keyword arguments to filter.

    Returns:
        Filtered dict with sentinel values removed and tuples converted to lists.
    """
    result: dict[str, Any] = {}
    for k, v in kwargs.items():
        if v is None or v == ():
            continue
        if isinstance(v, tuple):
            result[k] = list(cast("tuple[Any, ...]", v))
        else:
            result[k] = v
    return result


def apply_validated_overrides(base_config: EmailConfig, overrides: dict[str, Any]) -> EmailConfig:
    """Apply overrides with full Pydantic validation.

    Uses model_validate() with a merged dict instead of model_copy(update=...)
    to ensure Pydantic validators run on all overridden values.

    Args:
        base_config: Base EmailConfig to merge overrides into.
        overrides: Dict of field values to override (already filtered).

    Returns:
        New EmailConfig with overrides applied and validated.

    Raises:
        ValidationError: When overrides contain invalid values.
    """
    if not overrides:
        return base_config
    base_dict = base_config.model_dump()
    merged = {**base_dict, **overrides}
    return EmailConfig.model_validate(merged)


def smtp_config_options(func: Callable[..., Any]) -> Callable[..., Any]:
    """Apply shared SMTP configuration override options to a Click command.

    Adds CLI flags for all EmailConfig fields so that any TOML setting
    can be overridden at invocation time.
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
            "--raise-on-missing-attachments/--no-raise-on-missing-attachments",
            default=None,
            help="Override missing attachment handling",
        ),
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

    if not email_config.smtp_hosts:
        logger.error("No SMTP hosts configured")
        click.echo(
            "\nError: No SMTP hosts configured. Please configure email.smtp_hosts in your config file.", err=True
        )
        click.echo(f"See: {__init__conf__.shell_command} config-deploy --target user", err=True)
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
        2. ValueError -> INVALID_ARGUMENT (2): Invalid parameters or email format
        3. FileNotFoundError -> FILE_NOT_FOUND (66): Missing attachment (if enabled)
        4. DeliveryError/RuntimeError -> SMTP_FAILURE (69): SMTP transport failures
        5. Exception (catch-all) -> GENERAL_ERROR (1): Unexpected errors with traceback

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
        click.echo(f"Error: {heading}: {problem}", err=True)
    get_current_context().exit(exit_code)


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
        click.echo(f"\n{message_type} sent successfully!")
        logger.info("%s sent via CLI", message_type, extra={"recipients": recipients})
    else:
        click.echo(f"\n{message_type} sending failed.", err=True)
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
    click.echo(f"\nError: {user_message} - {exc}", err=True)
    get_current_context().exit(exit_code)


__all__ = [
    "apply_validated_overrides",
    "execute_with_email_error_handling",
    "filter_sentinels",
    "handle_validation_error",
    "load_and_validate_email_config",
    "smtp_config_options",
]
