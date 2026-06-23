"""Pure domain value objects for backup operations."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ServerConfig:
    """Immutable configuration for a single Proxmox server.

    Attributes:
        name: Short identifier used in filenames and logs.
        hostname: FQDN for SSH connections.
        zfs_pool: ZFS pool name to snapshot (typically "rpool").
        is_local: When True, commands run locally instead of over SSH.
        backup_configfiles: Whether to back up configuration files for this server.
        backup_snapshot: Whether to back up ZFS rpool snapshot for this server.

    Example:
        >>> srv = ServerConfig(name="proxmox01", hostname="proxmox01.local.rotek.at", zfs_pool="rpool")
        >>> srv.is_local
        False
        >>> srv.backup_configfiles
        True
        >>> srv.backup_snapshot
        True
    """

    name: str
    hostname: str
    zfs_pool: str
    is_local: bool = False
    backup_configfiles: bool = True
    backup_snapshot: bool = True


@dataclass(frozen=True, slots=True)
class BackupResult:
    """Outcome of backing up a single server.

    Skipped backup types (disabled in per-server config or filtered by CLI
    ``--type``) are marked via ``config_skipped`` / ``zfs_skipped`` and do
    not count as errors.

    Example:
        >>> r = BackupResult(server="proxmox01", config_ok=True, zfs_ok=True, duration_seconds=42.5)
        >>> r.has_errors
        False
        >>> r2 = BackupResult(server="fw", config_ok=True, zfs_skipped=True, duration_seconds=1.0)
        >>> r2.has_errors
        False
    """

    server: str
    config_ok: bool = False
    config_error: str = ""
    config_skipped: bool = False
    zfs_ok: bool = False
    zfs_error: str = ""
    zfs_skipped: bool = False
    duration_seconds: float = 0.0

    @property
    def has_errors(self) -> bool:
        """Return True if a non-skipped backup type failed.

        Example:
            >>> BackupResult(server="x", config_ok=True, zfs_ok=False, zfs_error="fail").has_errors
            True
            >>> BackupResult(server="x", config_ok=True, zfs_skipped=True).has_errors
            False
        """
        config_failed = not self.config_ok and not self.config_skipped
        zfs_failed = not self.zfs_ok and not self.zfs_skipped
        return config_failed or zfs_failed


@dataclass(frozen=True, slots=True)
class BackupSummary:
    """Aggregated results from backing up all servers.

    Example:
        >>> s = BackupSummary(results=(BackupResult(server="a", config_ok=True, zfs_ok=True),))
        >>> s.all_ok
        True
    """

    results: tuple[BackupResult, ...]
    total_duration_seconds: float = 0.0

    @property
    def all_ok(self) -> bool:
        """Return True if every server backup succeeded.

        Example:
            >>> s = BackupSummary(results=(BackupResult(server="a", config_ok=True, zfs_ok=True),))
            >>> s.all_ok
            True
        """
        return all(not r.has_errors for r in self.results)

    @property
    def failed_servers(self) -> tuple[BackupResult, ...]:
        """Return results for servers that had at least one failure.

        Example:
            >>> s = BackupSummary(results=(
            ...     BackupResult(server="a", config_ok=True, zfs_ok=True),
            ...     BackupResult(server="b", config_ok=False, config_error="fail"),
            ... ))
            >>> [r.server for r in s.failed_servers]
            ['b']
        """
        return tuple(r for r in self.results if r.has_errors)


__all__ = [
    "BackupResult",
    "BackupSummary",
    "ServerConfig",
]
