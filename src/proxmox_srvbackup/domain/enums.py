"""Type-safe domain enums for output formats, deployment targets, and backup types."""

from __future__ import annotations

from enum import Enum, StrEnum


class OutputFormat(str, Enum):
    """Output format options for configuration display.

    Defines valid output format choices for the config command.
    Inherits from str to allow direct string comparison and Click integration.

    Attributes:
        HUMAN: Human-readable TOML-like output format.
        JSON: Machine-readable JSON output format.

    Example:
        >>> OutputFormat.HUMAN.value
        'human'
        >>> OutputFormat.JSON == "json"
        True
    """

    HUMAN = "human"
    JSON = "json"


class DeployTarget(str, Enum):
    """Configuration deployment target layers.

    Defines valid target layers for configuration file deployment.
    Inherits from str to allow direct string comparison and Click integration.

    Attributes:
        APP: System-wide application configuration (requires privileges).
        HOST: System-wide host-specific configuration (requires privileges).
        USER: User-specific configuration (~/.config on Linux).

    Example:
        >>> DeployTarget.USER.value
        'user'
        >>> DeployTarget.APP == "app"
        True
    """

    APP = "app"
    HOST = "host"
    USER = "user"


class BackupType(StrEnum):
    """Backup operation scope.

    Attributes:
        CONFIG: Back up configuration files only.
        ZFS: Back up ZFS rpool snapshot only.
        ALL: Back up both configuration and ZFS snapshot.

    Example:
        >>> BackupType.CONFIG.value
        'config'
        >>> BackupType.ALL == "all"
        True
    """

    CONFIG = "config"
    ZFS = "zfs"
    ALL = "all"


__all__ = [
    "BackupType",
    "DeployTarget",
    "OutputFormat",
]
