"""Email sending CLI commands.

Provides commands for sending emails and notifications via SMTP.

Contents:
    * :func:`.send_email.cli_send_email` - Send email with optional HTML and attachments.
    * :func:`.send_notification.cli_send_notification` - Send simple plain-text notification.
    * :class:`._common.EmailConfigOverrides` - The SMTP options a command line gave, typed.
"""

from __future__ import annotations

from ._common import EmailConfigOverrides
from .send_email import cli_send_email
from .send_notification import cli_send_notification

__all__ = ["EmailConfigOverrides", "cli_send_email", "cli_send_notification"]
