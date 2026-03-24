"""Basic CLI commands for info, greeting, and failure testing.

Provides simple commands that demonstrate success and failure paths.

Contents:
    * :func:`cli_info` - Display package metadata.
    * :func:`cli_hello` - Emit canonical greeting.
    * :func:`cli_fail` - Trigger intentional failure for testing.
"""

from __future__ import annotations

import logging

import lib_log_rich.runtime
import rich_click as click

from proxmox_srvbackup import __init__conf__
from proxmox_srvbackup.domain.behaviors import build_greeting

from ..constants import CLICK_CONTEXT_SETTINGS

logger = logging.getLogger(__name__)


@click.command("info", context_settings=CLICK_CONTEXT_SETTINGS)
def cli_info() -> None:
    """Print resolved metadata so users can inspect installation details.

    Example:
        >>> from click.testing import CliRunner
        >>> runner = CliRunner()
        >>> result = runner.invoke(cli_info)
        >>> result.exit_code == 0
        True
    """
    with lib_log_rich.runtime.bind(job_id="cli-info", extra={"command": "info"}):
        logger.info("Displaying package information")
        __init__conf__.print_info()


@click.command("hello", context_settings=CLICK_CONTEXT_SETTINGS)
def cli_hello() -> None:
    """Demonstrate the success path by emitting the canonical greeting.

    Example:
        >>> from click.testing import CliRunner
        >>> runner = CliRunner()
        >>> result = runner.invoke(cli_hello)
        >>> "Hello World" in result.output
        True
    """
    with lib_log_rich.runtime.bind(job_id="cli-hello", extra={"command": "hello"}):
        logger.info("Executing hello command")
        click.echo(build_greeting())


@click.command("fail", context_settings=CLICK_CONTEXT_SETTINGS)
def cli_fail() -> None:
    """Trigger the intentional failure helper to test error handling.

    Example:
        >>> from click.testing import CliRunner
        >>> runner = CliRunner()
        >>> result = runner.invoke(cli_fail)
        >>> result.exit_code != 0
        True
    """
    with lib_log_rich.runtime.bind(job_id="cli-fail", extra={"command": "fail"}):
        logger.warning("Executing intentional failure command")
        raise RuntimeError("I should fail")


__all__ = ["cli_fail", "cli_hello", "cli_info"]
