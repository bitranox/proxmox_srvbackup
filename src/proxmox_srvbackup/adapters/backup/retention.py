"""Backup file retention management.

Prunes old backup files from local directories, keeping only the newest N
files matching a given glob pattern. Runs locally on proxmox-pbs.
"""

from __future__ import annotations

import logging
from pathlib import Path

from proxmox_srvbackup.domain.errors import RetentionError

logger = logging.getLogger(__name__)


def apply_retention(directory: Path, *, pattern: str = "*", keep: int = 3) -> list[Path]:
    """Keep the newest ``keep`` files matching ``pattern``, delete the rest.

    Files are sorted lexicographically by name. Since backup filenames embed
    timestamps in ``YYYY-MM-DD_HH-MM-SS`` format, lexicographic order equals
    chronological order.

    Args:
        directory: Local directory containing backup files.
        pattern: Glob pattern to match files (default: all files).
        keep: Number of newest files to retain.

    Returns:
        List of deleted file paths.

    Raises:
        RetentionError: If a file cannot be deleted.
    """
    if not directory.is_dir():
        logger.debug("Retention directory does not exist: %s", directory)
        return []

    files = sorted(
        (f for f in directory.glob(pattern) if f.is_file()),
        key=lambda p: p.name,
    )

    if len(files) <= keep:
        logger.debug("Retention: %d files, keeping %d — nothing to prune", len(files), keep)
        return []

    to_delete = files[: len(files) - keep]
    deleted: list[Path] = []

    for path in to_delete:
        try:
            path.unlink()
            logger.info("Retention: deleted %s", path)
            deleted.append(path)
        except OSError as exc:  # noqa: PERF203
            raise RetentionError(f"Cannot delete {path}: {exc}") from exc

    return deleted


__all__ = ["apply_retention"]
