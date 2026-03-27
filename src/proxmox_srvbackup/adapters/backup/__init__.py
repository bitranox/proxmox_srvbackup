"""Backup adapter package.

Provides infrastructure implementations for pulling backups from Proxmox
servers, managing retention, and orchestrating parallel backup operations.
"""

from __future__ import annotations

from .config_backup import backup_config
from .orchestrator import backup_all, backup_server
from .packages_backup import backup_packages
from .retention import apply_retention
from .setup_keys import setup_keys
from .zfs_backup import backup_zfs

__all__ = [
    "apply_retention",
    "backup_all",
    "backup_config",
    "backup_packages",
    "backup_server",
    "backup_zfs",
    "setup_keys",
]
