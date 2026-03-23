"""Pure domain functions with no I/O or framework dependencies."""

from __future__ import annotations

from datetime import datetime, timezone

from .models import (
    BackupResult,  # noqa: F401  # pyright: ignore[reportUnusedImport] — used in doctests
    BackupSummary,
)

CANONICAL_GREETING = "Hello World"


def build_greeting() -> str:
    r"""Return the canonical greeting string.

    Provide a deterministic success path that the documentation, smoke
    tests, and packaging checks can rely on while the real domain logic
    is developed.

    Returns:
        The canonical greeting string.

    Example:
        >>> build_greeting()
        'Hello World'
    """
    return CANONICAL_GREETING


def build_timestamp() -> str:
    """Return a filesystem-safe timestamp for backup filenames.

    Example:
        >>> ts = build_timestamp()
        >>> len(ts.split("_"))  # date_time parts
        2
    """
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")


def build_config_filename(server: str, timestamp: str) -> str:
    """Return the filename for a config backup archive.

    Example:
        >>> build_config_filename("proxmox01", "2026-03-23_04-30-00")
        'backup_config_proxmox01_2026-03-23_04-30-00.tar.gz'
    """
    return f"backup_config_{server}_{timestamp}.tar.gz"


def build_snapshot_filename(server: str, pool: str, timestamp: str) -> str:
    """Return the filename for a ZFS snapshot archive.

    Example:
        >>> build_snapshot_filename("proxmox01", "rpool", "2026-03-23_04-30-00")
        'rpool_snapshot_proxmox01_2026-03-23_04-30-00.zfs.gz'
    """
    return f"{pool}_snapshot_{server}_{timestamp}.zfs.gz"


def build_snapshot_tag(timestamp: str) -> str:
    """Return the ZFS snapshot name tag.

    Example:
        >>> build_snapshot_tag("2026-03-23_04-30-00")
        'pull_backup_2026-03-23_04-30-00'
    """
    return f"pull_backup_{timestamp}"


def build_summary_report(summary: BackupSummary) -> str:
    """Format a backup summary into a human-readable report.

    Example:
        >>> s = BackupSummary(
        ...     results=(BackupResult(server="px01", config_ok=True, zfs_ok=True, duration_seconds=10.5),),
        ...     total_duration_seconds=10.5,
        ... )
        >>> "px01" in build_summary_report(s)
        True
    """
    lines: list[str] = []
    lines.append(f"Backup completed in {summary.total_duration_seconds:.1f}s")
    lines.append(f"Servers: {len(summary.results)} total, {len(summary.failed_servers)} failed")
    lines.append("")

    for result in summary.results:
        status = "OK" if not result.has_errors else "FAILED"
        lines.append(f"  {result.server}: {status} ({result.duration_seconds:.1f}s)")
        if result.config_skipped:
            lines.append("    config: skipped (disabled)")
        if result.config_error:
            lines.append(f"    config error: {result.config_error}")
        if result.zfs_skipped:
            lines.append("    zfs: skipped (disabled)")
        if result.zfs_error:
            lines.append(f"    zfs error: {result.zfs_error}")

    return "\n".join(lines)


def build_summary_subject(summary: BackupSummary) -> str:
    """Return an email subject line with status tag.

    Example:
        >>> s = BackupSummary(results=(BackupResult(server="a", config_ok=True, zfs_ok=True),))
        >>> build_summary_subject(s)
        '[OK] Proxmox Backup Summary'
    """
    if summary.all_ok:
        return "[OK] Proxmox Backup Summary"
    if len(summary.failed_servers) == len(summary.results):
        return "[ERROR] Proxmox Backup Summary"
    return "[WARNING] Proxmox Backup Summary"


__all__ = [
    "CANONICAL_GREETING",
    "build_config_filename",
    "build_greeting",
    "build_snapshot_filename",
    "build_snapshot_tag",
    "build_summary_report",
    "build_summary_subject",
    "build_timestamp",
]
