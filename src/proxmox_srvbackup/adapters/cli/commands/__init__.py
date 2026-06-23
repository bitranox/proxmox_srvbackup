"""CLI command implementations.

Collects all subcommand functions and re-exports them for registration
with the root CLI group.

Contents:
    * Info commands from :mod:`.info`
    * Config commands from :mod:`.config`
    * Email commands from :mod:`.email` (subpackage)
    * Logging commands from :mod:`.logging`
    * Backup commands from :mod:`.backup`
"""

from __future__ import annotations

from .backup import cli_backup, cli_setup_keys
from .config import cli_config, cli_config_deploy, cli_config_generate_examples
from .email import cli_send_email, cli_send_notification
from .info import cli_fail, cli_hello, cli_info
from .logging import cli_logdemo

__all__ = [
    "cli_backup",
    "cli_config",
    "cli_config_deploy",
    "cli_config_generate_examples",
    "cli_fail",
    "cli_hello",
    "cli_info",
    "cli_logdemo",
    "cli_send_email",
    "cli_send_notification",
    "cli_setup_keys",
]
