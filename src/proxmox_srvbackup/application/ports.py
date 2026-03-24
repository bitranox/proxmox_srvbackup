"""Application ports — callable Protocol definitions for adapter functions.

Each Protocol class defines a ``__call__`` method whose signature exactly
matches the corresponding adapter function.  Existing module-level functions
satisfy these protocols automatically via structural subtyping (PEP 544).

System Role:
    Sits between domain and adapters.  Infrastructure types (``Config``,
    ``EmailConfig``) are imported under ``TYPE_CHECKING`` only so that
    import-linter layer contracts remain satisfied at runtime.
"""

from __future__ import annotations

import subprocess  # nosec B404
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from ..domain.enums import BackupType, DeployTarget, OutputFormat
from ..domain.models import BackupResult, BackupSummary, ServerConfig

if TYPE_CHECKING:
    from lib_layered_config import Config

    from ..adapters.email.sender import EmailConfig


class GetConfig(Protocol):
    """Load layered configuration with application defaults."""

    def __call__(
        self, *, profile: str | None = ..., start_dir: str | None = ..., dotenv_path: str | None = ...
    ) -> Config: ...


class GetDefaultConfigPath(Protocol):
    """Return the path to the bundled default configuration file."""

    def __call__(self) -> Path: ...


class DeployConfiguration(Protocol):
    """Deploy default configuration to specified target layers."""

    def __call__(
        self,
        *,
        targets: Sequence[DeployTarget],
        force: bool = ...,
        profile: str | None = ...,
        set_permissions: bool = ...,
        dir_mode: int | None = ...,
        file_mode: int | None = ...,
    ) -> list[Path]: ...


class DisplayConfig(Protocol):
    """Display the provided configuration in the requested format."""

    def __call__(
        self, config: Config, *, output_format: OutputFormat = ..., section: str | None = ..., profile: str | None = ...
    ) -> None: ...


class SendEmail(Protocol):
    """Send an email using configured SMTP settings."""

    def __call__(
        self,
        *,
        config: EmailConfig,
        recipients: str | Sequence[str] | None = ...,
        subject: str,
        body: str = ...,
        body_html: str = ...,
        from_address: str | None = ...,
        attachments: Sequence[Path] | None = ...,
    ) -> bool: ...


class SendNotification(Protocol):
    """Send a simple plain-text notification email."""

    def __call__(
        self,
        *,
        config: EmailConfig,
        recipients: str | Sequence[str] | None = ...,
        subject: str,
        message: str,
        from_address: str | None = ...,
    ) -> bool: ...


class LoadEmailConfigFromDict(Protocol):
    """Load EmailConfig from a configuration dictionary."""

    def __call__(self, config_dict: Mapping[str, Any]) -> EmailConfig: ...


class InitLogging(Protocol):
    """Initialize lib_log_rich runtime with the provided configuration."""

    def __call__(self, config: Config) -> None: ...


class RunRemoteCommand(Protocol):
    """Execute a command on a remote host via SSH."""

    def __call__(
        self,
        host: str,
        command: str,
        *,
        ssh_key: str,
        user: str = ...,
        timeout: int = ...,
    ) -> subprocess.CompletedProcess[str]: ...


class PipeRemoteToFile(Protocol):
    """Stream remote command stdout to a local file via SSH."""

    def __call__(
        self,
        host: str,
        command: str,
        local_path: Path,
        *,
        ssh_key: str,
        user: str = ...,
    ) -> None: ...


class BackupServerConfig(Protocol):
    """Pull configuration backup from a single server."""

    def __call__(
        self,
        server: ServerConfig,
        *,
        backup_dir: Path,
        config_paths: Sequence[str],
        exclude_patterns: Sequence[str],
        ssh_key: str,
        ssh_user: str = ...,
        ssh_timeout: int = ...,
        retention_count: int = ...,
        dry_run: bool = ...,
    ) -> None: ...


class BackupServerZfs(Protocol):
    """Pull ZFS rpool snapshot from a single server."""

    def __call__(
        self,
        server: ServerConfig,
        *,
        backup_dir: Path,
        ssh_key: str,
        ssh_user: str = ...,
        ssh_timeout: int = ...,
        retention_count: int = ...,
        dry_run: bool = ...,
    ) -> None: ...


class ApplyRetention(Protocol):
    """Prune old backup files, keeping only the newest N."""

    def __call__(self, directory: Path, *, pattern: str = ..., keep: int = ...) -> list[Path]: ...


class SetupKeys(Protocol):
    """Generate per-server SSH keypairs and deploy public keys."""

    def __call__(
        self,
        servers: Sequence[ServerConfig],
        *,
        key_dir: Path,
        key_prefix: str,
        bootstrap_key: str,
        authorized_keys_path: str = ...,
    ) -> dict[str, bool]: ...


class BackupAllServers(Protocol):
    """Orchestrate backups across all configured servers."""

    def __call__(
        self,
        servers: Sequence[ServerConfig],
        *,
        config: Config,
        backup_types: BackupType = ...,
        max_parallel: int = ...,
        dry_run: bool = ...,
    ) -> BackupSummary: ...


class BackupSingleServer(Protocol):
    """Run backup for a single server and return the result."""

    def __call__(
        self,
        server: ServerConfig,
        *,
        config: Config,
        backup_types: BackupType = ...,
        dry_run: bool = ...,
    ) -> BackupResult: ...


__all__ = [
    "ApplyRetention",
    "BackupAllServers",
    "BackupServerConfig",
    "BackupServerZfs",
    "BackupSingleServer",
    "DeployConfiguration",
    "DisplayConfig",
    "GetConfig",
    "GetDefaultConfigPath",
    "InitLogging",
    "LoadEmailConfigFromDict",
    "PipeRemoteToFile",
    "RunRemoteCommand",
    "SendEmail",
    "SendNotification",
    "SetupKeys",
]
