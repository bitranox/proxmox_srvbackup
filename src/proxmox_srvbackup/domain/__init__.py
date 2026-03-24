"""Domain layer - pure business logic with no I/O or framework dependencies.

Contains entities, value objects, and domain services that form the core
business logic of the application.

Contents:
    * :mod:`.behaviors` - Core domain behaviors (greeting, backup filename builders)
    * :mod:`.enums` - Domain enumerations (OutputFormat, DeployTarget, BackupType)
    * :mod:`.errors` - Domain exception types
    * :mod:`.models` - Value objects (ServerConfig, BackupResult, BackupSummary)
"""

from __future__ import annotations

from .behaviors import (
    CANONICAL_GREETING,
    build_config_filename,
    build_greeting,
    build_snapshot_filename,
    build_snapshot_tag,
    build_summary_report,
    build_summary_subject,
    build_timestamp,
)
from .enums import BackupType, DeployTarget, OutputFormat
from .errors import (
    BackupError,
    ConfigurationError,
    DeliveryError,
    InvalidRecipientError,
    RetentionError,
    SnapshotError,
    SSHConnectionError,
)
from .models import BackupResult, BackupSummary, ServerConfig

__all__ = [
    # Behaviors
    "CANONICAL_GREETING",
    "build_config_filename",
    "build_greeting",
    "build_snapshot_filename",
    "build_snapshot_tag",
    "build_summary_report",
    "build_summary_subject",
    "build_timestamp",
    # Enums
    "BackupType",
    "DeployTarget",
    "OutputFormat",
    # Errors
    "BackupError",
    "ConfigurationError",
    "DeliveryError",
    "InvalidRecipientError",
    "RetentionError",
    "SSHConnectionError",
    "SnapshotError",
    # Models
    "BackupResult",
    "BackupSummary",
    "ServerConfig",
]
