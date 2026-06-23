"""SSH key generation and deployment for pull-based backups.

Generates per-server ed25519 keypairs on proxmox-pbs and deploys the public
keys to each remote server using the existing shared bootstrap key for
initial access.

Deploys keys directly via ``cat >>`` instead of ``ssh-copy-id`` because
Proxmox VE symlinks ``~/.ssh/authorized_keys`` to
``/etc/pve/priv/authorized_keys`` on a FUSE filesystem (pmxcfs) where
``ssh-copy-id`` silently fails.
"""

from __future__ import annotations

import logging
import subprocess  # nosec B404
from collections.abc import Sequence
from pathlib import Path

from proxmox_srvbackup.domain.models import ServerConfig

logger = logging.getLogger(__name__)


def _key_path(key_dir: Path, key_prefix: str, server_name: str) -> Path:
    """Return the private key path for a server."""
    return key_dir / f"{key_prefix}_{server_name}"


def _generate_keypair(key_file: Path, comment: str) -> bool:
    """Generate an ed25519 keypair if it does not already exist."""
    if key_file.exists():
        logger.info("Key already exists: %s — skipping generation", key_file)
        return True

    cmd = [
        "ssh-keygen",
        "-t",
        "ed25519",
        "-N",
        "",
        "-f",
        str(key_file),
        "-C",
        comment,
    ]
    logger.info("Generating keypair: %s", key_file)
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)  # noqa: S603  # nosec B603

    if result.returncode != 0:
        logger.error("Key generation failed for %s: %s", key_file, result.stderr.strip())
        return False

    key_file.chmod(0o600)
    return True


def _deploy_public_key(
    key_file: Path,
    hostname: str,
    bootstrap_key: str,
    authorized_keys_path: str,
    user: str = "root",
) -> bool:
    """Deploy the public key to a remote server via SSH cat.

    Reads the local public key and appends it to the remote
    ``authorized_keys_path`` if not already present. Uses the bootstrap
    key for authentication.

    This avoids ``ssh-copy-id`` which silently fails on Proxmox VE
    where ``~/.ssh/authorized_keys`` is a symlink to the pmxcfs FUSE
    filesystem at ``/etc/pve/priv/authorized_keys``.
    """
    pub_key_file = key_file.with_suffix(".pub")
    if not pub_key_file.exists():
        logger.error("Public key not found: %s", pub_key_file)
        return False

    pub_key_content = pub_key_file.read_text().strip()

    # Check if key is already deployed (idempotent)
    check_cmd = [
        "ssh",
        "-i",
        bootstrap_key,
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=10",
        f"{user}@{hostname}",
        f"grep -qF '{pub_key_content}' {authorized_keys_path} 2>/dev/null && echo FOUND || echo MISSING",
    ]
    logger.info("Checking if key already deployed on %s@%s", user, hostname)
    check_result = subprocess.run(check_cmd, capture_output=True, text=True, check=False)  # noqa: S603  # nosec B603

    if check_result.returncode == 0 and "FOUND" in check_result.stdout:
        logger.info("Key already present on %s — skipping deployment", hostname)
        return True

    # Append the key
    deploy_cmd = [
        "ssh",
        "-i",
        bootstrap_key,
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=10",
        f"{user}@{hostname}",
        f"echo '{pub_key_content}' >> {authorized_keys_path}",
    ]
    logger.info("Deploying public key to %s@%s:%s", user, hostname, authorized_keys_path)
    result = subprocess.run(deploy_cmd, capture_output=True, text=True, check=False)  # noqa: S603  # nosec B603

    if result.returncode != 0:
        logger.error("Key deployment failed for %s: %s", hostname, result.stderr.strip())
        return False

    return True


def _test_key(key_file: Path, hostname: str, user: str = "root") -> bool:
    """Test SSH connectivity using the new key."""
    cmd = [
        "ssh",
        "-i",
        str(key_file),
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=10",
        f"{user}@{hostname}",
        "hostname",
    ]
    logger.info("Testing key for %s@%s", user, hostname)
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)  # noqa: S603  # nosec B603

    if result.returncode == 0:
        logger.info("Key test successful for %s: %s", hostname, result.stdout.strip())
        return True

    logger.error("Key test failed for %s: %s", hostname, result.stderr.strip())
    return False


def setup_keys(
    servers: Sequence[ServerConfig],
    *,
    key_dir: Path,
    key_prefix: str,
    bootstrap_key: str,
    authorized_keys_path: str = "/etc/pve/priv/authorized_keys",
) -> dict[str, bool]:
    """Generate per-server SSH keypairs and deploy public keys.

    For each non-local server:
        1. Generate an ed25519 keypair (skip if already exists).
        2. Deploy the public key to the remote server's
           ``authorized_keys_path`` via SSH (skip if already present).
        3. Test connectivity using the new key.

    Args:
        servers: List of server configurations.
        key_dir: Directory to store keypairs (e.g., /root/.ssh).
        key_prefix: Filename prefix for keys (e.g., "backup_pull").
        bootstrap_key: Path to existing shared SSH key for initial deployment.
        authorized_keys_path: Remote path to authorized_keys file.
            Defaults to ``/etc/pve/priv/authorized_keys`` for Proxmox VE.

    Returns:
        Dictionary mapping server names to success status.
    """
    key_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, bool] = {}

    for server in servers:
        if server.is_local:
            logger.info("Skipping local server: %s", server.name)
            results[server.name] = True
            continue

        key_file = _key_path(key_dir, key_prefix, server.name)
        comment = f"proxmox-pbs-backup-pull-{server.name}"

        if not _generate_keypair(key_file, comment):
            results[server.name] = False
            continue

        if not _deploy_public_key(key_file, server.hostname, bootstrap_key, authorized_keys_path):
            results[server.name] = False
            continue

        results[server.name] = _test_key(key_file, server.hostname)

    return results


__all__ = ["setup_keys"]
