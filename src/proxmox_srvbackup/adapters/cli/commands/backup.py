"""Backup CLI commands for pulling backups and managing SSH keys.

Contents:
    * :func:`cli_backup` - Pull backups from configured Proxmox servers.
    * :func:`cli_setup_keys` - Generate and deploy per-server SSH keys.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import lib_log_rich.runtime
import rich_click as click

from proxmox_srvbackup.adapters.backup.orchestrator import extract_backup_settings
from proxmox_srvbackup.domain.behaviors import build_summary_report, build_summary_subject
from proxmox_srvbackup.domain.enums import BackupType
from proxmox_srvbackup.domain.models import BackupSummary, ServerConfig

from ..constants import CLICK_CONTEXT_SETTINGS
from ..context import CLIContext, get_cli_context
from ..exit_codes import ExitCode

logger = logging.getLogger(__name__)

_FALSY_STRINGS = frozenset({"false", "0", "no", "off", ""})


def _as_bool(value: object, default: bool) -> bool:
    """Coerce a config value to bool, handling strings from .env files.

    TOML values arrive as native ``bool``, but ``.env`` and environment
    variable overrides arrive as strings.  This helper normalises both.

    Example:
        >>> _as_bool(True, False)
        True
        >>> _as_bool("false", True)
        False
        >>> _as_bool("yes", False)
        True
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in _FALSY_STRINGS
    return default


def _servers_from_config(config: Mapping[str, Any]) -> list[ServerConfig]:
    """Parse server configurations from the backup config section."""
    servers_dict = config.get("backup", {}).get("servers", {})
    servers: list[ServerConfig] = []
    for name, srv_cfg in servers_dict.items():
        servers.append(
            ServerConfig(
                name=name,
                hostname=srv_cfg.get("hostname", ""),
                zfs_pool=srv_cfg.get("zfs_pool", "rpool"),
                is_local=_as_bool(srv_cfg.get("is_local", False), default=False),
                backup_configfiles=_as_bool(srv_cfg.get("backup_configfiles", True), default=True),
                backup_snapshot=_as_bool(srv_cfg.get("backup_snapshot", True), default=True),
            )
        )
    return sorted(servers, key=lambda s: s.name)


@click.command("backup", context_settings=CLICK_CONTEXT_SETTINGS)
@click.option(
    "--server",
    type=str,
    default=None,
    help="Backup only this server (by name from config).",
)
@click.option(
    "--type",
    "backup_type",
    type=click.Choice([t.value for t in BackupType], case_sensitive=False),
    default=BackupType.ALL.value,
    help="Type of backup to perform.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Show what would be executed without running backups.",
)
@click.pass_context
def cli_backup(ctx: click.Context, server: str | None, backup_type: str, dry_run: bool) -> None:
    """Pull backups from configured Proxmox servers.

    Connects to each server via SSH and pulls configuration archives and
    ZFS rpool snapshots to the local backup storage.

    Example:
        >>> from click.testing import CliRunner
        >>> runner = CliRunner()
        >>> # Real invocation tested in integration tests
    """
    cli_ctx = get_cli_context(ctx)
    config = cli_ctx.config
    bt = BackupType(backup_type.lower())

    extra = {"command": "backup", "type": bt.value, "dry_run": dry_run, "server_filter": server}
    with lib_log_rich.runtime.bind(job_id="cli-backup", extra=extra):
        servers = _servers_from_config(config.as_dict())

        if not servers:
            click.echo("No servers configured in [backup.servers] section.", err=True)
            raise SystemExit(ExitCode.GENERAL_ERROR)

        if server:
            servers = [s for s in servers if s.name == server]
            if not servers:
                click.echo(f"Server '{server}' not found in configuration.", err=True)
                raise SystemExit(ExitCode.INVALID_ARGUMENT)

        logger.info(
            "Starting backup: %d server(s), type=%s, dry_run=%s",
            len(servers),
            bt.value,
            dry_run,
        )

        if dry_run:
            click.echo(f"[DRY-RUN] Would backup {len(servers)} server(s):")
            for srv in servers:
                mode = "local" if srv.is_local else "ssh"
                types: list[str] = []
                if srv.backup_configfiles:
                    types.append("config")
                if srv.backup_snapshot:
                    types.append("zfs")
                types_str = "+".join(types) if types else "none"
                click.echo(f"  {srv.name} ({srv.hostname}) [{mode}] [{types_str}]")

        settings = extract_backup_settings(config)

        summary = cli_ctx.services.backup_all(
            servers,
            config=config,
            backup_types=bt,
            max_parallel=settings.max_parallel,
            dry_run=dry_run,
        )

        report = build_summary_report(summary)
        click.echo()
        click.echo(report)

        if not dry_run:
            _send_summary_email(cli_ctx, summary, report)

        if not summary.all_ok:
            raise SystemExit(ExitCode.GENERAL_ERROR)


def _send_summary_email(cli_ctx: CLIContext, summary: BackupSummary, report: str) -> None:
    """Send backup summary notification email."""
    try:
        email_config = cli_ctx.services.load_email_config_from_dict(cli_ctx.config.as_dict().get("email", {}))
        subject = build_summary_subject(summary)
        cli_ctx.services.send_notification(
            config=email_config,
            subject=subject,
            message=report,
        )
        logger.info("Summary email sent: %s", subject)
    except Exception as exc:
        logger.error("Failed to send summary email: %s", exc)


@click.command("setup-keys", context_settings=CLICK_CONTEXT_SETTINGS)
@click.pass_context
def cli_setup_keys(ctx: click.Context) -> None:
    """Generate and deploy per-server SSH keys for pull-based backups.

    For each configured server, generates an ed25519 keypair and deploys
    the public key using the bootstrap key for initial access.

    Example:
        >>> from click.testing import CliRunner
        >>> runner = CliRunner()
        >>> # Real invocation tested in integration tests
    """
    cli_ctx = get_cli_context(ctx)
    config = cli_ctx.config

    extra = {"command": "setup-keys"}
    with lib_log_rich.runtime.bind(job_id="cli-setup-keys", extra=extra):
        servers = _servers_from_config(config.as_dict())
        settings = extract_backup_settings(config)

        if not settings.bootstrap_key:
            click.echo("No bootstrap_key configured in [backup] section.", err=True)
            raise SystemExit(ExitCode.GENERAL_ERROR)

        click.echo(f"Setting up SSH keys for {len(servers)} server(s)...")
        click.echo(f"  Key directory: {settings.ssh_key_dir}")
        click.echo(f"  Key prefix: {settings.ssh_key_prefix}")
        click.echo(f"  Bootstrap key: {settings.bootstrap_key}")
        click.echo()

        results = cli_ctx.services.setup_keys(
            servers,
            key_dir=Path(settings.ssh_key_dir),
            key_prefix=settings.ssh_key_prefix,
            bootstrap_key=settings.bootstrap_key,
        )

        all_ok = True
        for name, success in sorted(results.items()):
            status = "OK" if success else "FAILED"
            symbol = "+" if success else "!"
            click.echo(f"  [{symbol}] {name}: {status}")
            if not success:
                all_ok = False

        if not all_ok:
            click.echo("\nSome key deployments failed. Check the log for details.", err=True)
            raise SystemExit(ExitCode.GENERAL_ERROR)

        click.echo("\nAll keys deployed successfully.")


__all__ = ["cli_backup", "cli_setup_keys"]
