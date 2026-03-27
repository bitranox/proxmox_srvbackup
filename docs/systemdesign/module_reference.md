# Module Reference: Architecture & File Index

## Status

Complete (v1.8.0)

---

## Related Files

### Domain Layer
- `src/proxmox_srvbackup/domain/behaviors.py` — Pure domain functions (greeting, timestamp, filename builders, summary formatting)
- `src/proxmox_srvbackup/domain/enums.py` — Type-safe enums (OutputFormat, DeployTarget, BackupType)
- `src/proxmox_srvbackup/domain/errors.py` — Domain exceptions (ConfigurationError, DeliveryError, SSHConnectionError, SnapshotError, RetentionError, etc.)
- `src/proxmox_srvbackup/domain/models.py` — Value objects (ServerConfig, BackupResult, BackupSummary)

### Application Layer
- `src/proxmox_srvbackup/application/ports.py` — Callable Protocol definitions for adapter functions

### Adapters Layer — Backup
- `src/proxmox_srvbackup/adapters/backup/orchestrator.py` — Parallel backup execution across servers (BackupSettings, backup_all, backup_server)
- `src/proxmox_srvbackup/adapters/backup/config_backup.py` — Pull config tar archives from remote servers via SSH pipe
- `src/proxmox_srvbackup/adapters/backup/packages_backup.py` — Capture `dpkg --get-selections` and `dpkg -l` from each server
- `src/proxmox_srvbackup/adapters/backup/zfs_backup.py` — Pull ZFS rpool recursive snapshots via SSH pipe
- `src/proxmox_srvbackup/adapters/backup/retention.py` — Prune old backups (keep N newest matching a glob pattern)
- `src/proxmox_srvbackup/adapters/backup/setup_keys.py` — Generate/deploy per-server ed25519 SSH keys

### Adapters Layer — SSH
- `src/proxmox_srvbackup/adapters/ssh/commands.py` — ssh_run, ssh_pipe_to_file, local_run, local_pipe_to_file

### Adapters Layer — Configuration
- `src/proxmox_srvbackup/adapters/config/loader.py` — Configuration loading with LRU caching
- `src/proxmox_srvbackup/adapters/config/deploy.py` — Configuration deployment
- `src/proxmox_srvbackup/adapters/config/display.py` — Configuration display (TOML/JSON output, redaction)
- `src/proxmox_srvbackup/adapters/config/overrides.py` — CLI `--set` override parsing and deep-merge
- `src/proxmox_srvbackup/adapters/config/permissions.py` — File permission handling for deploy targets

### Adapters Layer — Email
- `src/proxmox_srvbackup/adapters/email/config.py` — EmailConfig Pydantic model and loader
- `src/proxmox_srvbackup/adapters/email/transport.py` — SMTP send functions
- `src/proxmox_srvbackup/adapters/email/sender.py` — Re-exports (backward compat)
- `src/proxmox_srvbackup/adapters/email/validation.py` — Email address validation

### Adapters Layer — Logging
- `src/proxmox_srvbackup/adapters/logging/setup.py` — lib_log_rich initialization

### Adapters Layer — CLI
- `src/proxmox_srvbackup/adapters/cli/` — CLI adapter package:
  - `__init__.py` — Public facade
  - `constants.py` — Shared constants
  - `exit_codes.py` — POSIX exit codes (ExitCode IntEnum)
  - `context.py` — Click context helpers
  - `root.py` — Root command group
  - `main.py` — Entry point (accepts services_factory)
  - `commands/backup.py` — backup, setup-keys commands
  - `commands/info.py` — info, hello, fail commands
  - `commands/config.py` — config, config-deploy, config-generate-examples commands
  - `commands/logging.py` — logdemo command
  - `commands/email/` — Email commands subpackage:
    - `__init__.py` — Public exports
    - `_common.py` — Shared helpers (config loading, error handling, SMTP option decorators)
    - `send_email.py` — send-email command
    - `send_notification.py` — send-notification command

### Adapters Layer (In-Memory / Testing)
- `src/proxmox_srvbackup/adapters/memory/backup.py` — In-memory backup adapter (no-op)
- `src/proxmox_srvbackup/adapters/memory/config.py` — In-memory config adapters
- `src/proxmox_srvbackup/adapters/memory/email.py` — In-memory email adapters (spy)
- `src/proxmox_srvbackup/adapters/memory/logging.py` — In-memory logging (no-op)

### Composition Layer
- `src/proxmox_srvbackup/composition/__init__.py` — Wires adapters to ports (build_production, build_testing)

### Entry Points
- `src/proxmox_srvbackup/entry.py` — Console script entry point with production wiring
- `src/proxmox_srvbackup/__main__.py` — Thin shim for `python -m`
- `src/proxmox_srvbackup/__init__.py` — Public API exports
- `src/proxmox_srvbackup/__init__conf__.py` — Package metadata constants

### Configuration Defaults
- `src/proxmox_srvbackup/adapters/config/defaultconfig.toml` — Base defaults
- `src/proxmox_srvbackup/adapters/config/defaultconfig.d/40-layered-config.toml` — lib_layered_config integration docs
- `src/proxmox_srvbackup/adapters/config/defaultconfig.d/50-mail.toml` — Email defaults
- `src/proxmox_srvbackup/adapters/config/defaultconfig.d/60-backup.toml` — Backup configuration and server definitions
- `src/proxmox_srvbackup/adapters/config/defaultconfig.d/90-logging.toml` — Logging defaults
- `src/proxmox_srvbackup/adapters/config/systemd/` — Systemd timer/service units for automated backups

### Tests
- `tests/test_backup_adapters.py` — Backup adapter pure-logic tests (retention, tar command, SSH command, key path, orchestrator)
- `tests/test_backup_per_server.py` — Per-server backup type control (_as_bool, _servers_from_config, skip semantics, dry-run)
- `tests/test_behaviors.py` — Domain function tests (greeting, timestamp, filename builders, summary formatting)
- `tests/test_cache_effectiveness.py` — LRU cache behavior tests
- `tests/test_cli_config.py` — CLI config command tests (display, JSON format, section filtering, deploy, profile, redaction)
- `tests/test_cli_core.py` — Core CLI tests (traceback, main entry, help, hello, fail, info)
- `tests/test_cli_email.py` — Email CLI integration tests (send-email, send-notification, SMTP overrides)
- `tests/test_cli_env_file.py` — CLI `--env-file` option tests (path validation, value override)
- `tests/test_cli_exit_codes.py` — Exit code integration tests
- `tests/test_cli_overrides.py` — CLI `--set` override integration tests
- `tests/test_cli_validation.py` — Profile name validation tests
- `tests/test_config_overrides.py` — Unit tests for override parsing (parse_override, coerce_value, apply_overrides)
- `tests/test_deploy_permissions.py` — Permission option tests
- `tests/test_display.py` — Config display formatting tests
- `tests/test_enums.py` — Domain enum tests
- `tests/test_errors.py` — Domain error type tests
- `tests/test_logging.py` — Logging configuration model tests
- `tests/test_mail.py` — Email configuration and sending tests
- `tests/test_metadata.py` — Package metadata tests (PEP 561 marker, pyproject.toml sync)
- `tests/test_metadata_sync.py` — __init__conf__ constant sync tests
- `tests/test_module_entry.py` — `python -m` entry tests
- `tests/test_packages_backup.py` — Package list backup adapter tests (filename, dpkg output, retention, dry-run, local/remote)
- `tests/test_ports.py` — Protocol conformance tests
- `tests/test_property_email.py` — Property-based email validation tests (hypothesis)
- `tests/test_property_overrides.py` — Property-based override tests (hypothesis)
- `tests/test_ssh_commands.py` — SSH/local command unit tests (mocked subprocess)
- `tests/test_summary_report.py` — Summary report and subject formatting tests

---

## Architecture

### Layer Assignments

| Directory/Module | Layer | Responsibility |
|------------------|-------|----------------|
| `domain/` | Domain | Pure logic — no I/O, logging, or frameworks |
| `application/ports.py` | Application | Protocol definitions for adapters |
| `adapters/backup/` | Adapters | Backup orchestration, config/ZFS/packages backup, retention, SSH key setup |
| `adapters/ssh/` | Adapters | SSH command execution and file streaming |
| `adapters/config/` | Adapters | Configuration loading, deployment, display, permissions |
| `adapters/email/` | Adapters | SMTP email sending, validation |
| `adapters/logging/` | Adapters | lib_log_rich initialization |
| `adapters/cli/` | Adapters | Click CLI framework integration |
| `adapters/memory/` | Adapters | In-memory implementations for testing |
| `composition/` | Composition | Wires adapters to ports |

### Import Enforcement

Layer boundaries enforced via `import-linter` contracts in `pyproject.toml`:
- **Domain is pure**: Cannot import from adapters or composition
- **Clean Architecture layers**: Validates dependency direction (composition → adapters → application → domain)

Run `lint-imports` to verify compliance.

---

## Exit Codes

POSIX-conventional exit codes defined in `adapters/cli/exit_codes.py`:

| Code | Name | Usage |
|------|------|-------|
| 0 | `SUCCESS` | Command completed successfully |
| 1 | `GENERAL_ERROR` | Unhandled exception, general failure |
| 2 | `FILE_NOT_FOUND` | Attachment or file not found |
| 13 | `PERMISSION_DENIED` | Cannot write to target directory |
| 22 | `INVALID_ARGUMENT` | Invalid CLI argument or section not found |
| 69 | `SMTP_FAILURE` | SMTP delivery failed |
| 78 | `CONFIG_ERROR` | Missing required configuration |
| 110 | `TIMEOUT` | Operation timed out |
| 130 | `SIGNAL_INT` | Interrupted (SIGINT/Ctrl+C) |
| 141 | `BROKEN_PIPE` | Output pipe closed |
| 143 | `SIGNAL_TERM` | Terminated (SIGTERM) |

---

## CLI Commands

### Root Command

**Command:** `proxmox-srvbackup`

| Option | Description |
|--------|-------------|
| `--version` | Show version and exit |
| `--traceback / --no-traceback` | Show full Python traceback on errors |
| `--profile NAME` | Load configuration from a named profile |
| `--set SECTION.KEY=VALUE` | Override configuration setting (repeatable) |
| `--env-file PATH` | Explicit `.env` file path (skips upward directory search) |
| `-h, --help` | Show help and exit |

### backup

Pull backups from all configured Proxmox servers.

| Option | Description |
|--------|-------------|
| `--server NAME` | Backup only this server (by name from config) |
| `--type [all\|config\|zfs]` | Backup type filter (default: all) |
| `--dry-run` | Show what would be executed without running backups |

**Exit codes:** 0, 1

### setup-keys

Generate per-server ed25519 keypairs and deploy public keys to remote servers.

**Exit codes:** 0, 1

### info

Print resolved package metadata.

**Exit codes:** 0

### hello

Emit canonical greeting (`"Hello World"`).

**Exit codes:** 0

### fail

Trigger intentional `RuntimeError` for testing error handling.

**Exit codes:** 1

### config

Display merged configuration from all sources.

| Option | Description |
|--------|-------------|
| `--format [human\|json]` | Output format (default: human) |
| `--section NAME` | Show only specific section |

**Exit codes:** 0, 22 (section not found)

### config-deploy

Deploy default configuration to system or user directories.

| Option | Description |
|--------|-------------|
| `--target [app\|host\|user]` | Target layer(s) — required, repeatable |
| `--force` | Overwrite existing files |
| `--profile NAME` | Deploy to profile subdirectory |
| `--permissions / --no-permissions` | Enable/disable Unix permission setting |
| `--dir-mode MODE` | Override directory permissions (octal) |
| `--file-mode MODE` | Override file permissions (octal) |

**Exit codes:** 0, 1, 13 (permission denied)

### config-generate-examples

Generate example configuration files.

| Option | Description |
|--------|-------------|
| `--destination DIR` | Target directory — required |
| `--force` | Overwrite existing files |

**Exit codes:** 0, 1

### send-email

Send email using configured SMTP settings.

| Option | Description |
|--------|-------------|
| `--to ADDRESS` | Recipient (repeatable) |
| `--subject TEXT` | Subject line — required |
| `--body TEXT` | Plain-text body |
| `--body-html TEXT` | HTML body |
| `--from ADDRESS` | Override sender |
| `--attachment PATH` | File to attach (repeatable) |
| `--smtp-host HOST:PORT` | Override SMTP host (repeatable) |
| `--smtp-username USER` | Override username |
| `--smtp-password PASS` | Override password |
| `--use-starttls / --no-use-starttls` | Override STARTTLS |
| `--timeout SECONDS` | Override timeout |

**Exit codes:** 0, 2 (file not found), 22, 69 (SMTP failure), 78 (no SMTP hosts)

### send-notification

Send simple plain-text notification email.

| Option | Description |
|--------|-------------|
| `--to ADDRESS` | Recipient (repeatable) |
| `--subject TEXT` | Subject — required |
| `--message TEXT` | Message — required |
| `--from ADDRESS` | Override sender |
| `--smtp-host HOST:PORT` | Override SMTP host (repeatable) |
| `--smtp-username USER` | Override username |
| `--smtp-password PASS` | Override password |
| `--use-starttls / --no-use-starttls` | Override STARTTLS |
| `--timeout SECONDS` | Override timeout |

**Exit codes:** 0, 22, 69 (SMTP failure), 78 (no SMTP hosts)

### logdemo

Run logging demonstration.

| Option | Description |
|--------|-------------|
| `--theme NAME` | Logging theme (default: classic) |

**Exit codes:** 0

---

## Profile Validation

Profile names (`--profile` option) are validated using `lib_layered_config.validate_profile_name()`.

### validate_profile()

**Location:** `adapters/config/loader.py`

```python
def validate_profile(profile: str, max_length: int | None = None) -> None:
    """Validate profile name using lib_layered_config."""
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `profile` | `str` | required | Profile name to validate |
| `max_length` | `int \| None` | 64 | Maximum length (DEFAULT_MAX_PROFILE_LENGTH) |

### Validation Rules

| Rule | Description |
|------|-------------|
| Maximum length | 64 characters (configurable via `max_length`) |
| Character set | ASCII alphanumeric, hyphens (`-`), underscores (`_`) |
| Start character | Must start with alphanumeric character |
| Empty string | Rejected |
| Windows reserved | CON, PRN, AUX, NUL, COM1-9, LPT1-9 rejected |
| Path traversal | `/`, `\`, `..` rejected |
| Control chars | Rejected |

### Error Handling

Raises `ValueError` with descriptive message on invalid input.

---

## Email Configuration

### EmailConfig Fields

The `EmailConfig` Pydantic model (`adapters/email/config.py`) provides validated, immutable email configuration:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `smtp_hosts` | `list[str]` | `[]` | SMTP servers in `host[:port]` format |
| `from_address` | `str \| None` | `None` | Default sender address |
| `recipients` | `list[str]` | `[]` | Default recipient addresses |
| `smtp_username` | `str \| None` | `None` | SMTP authentication username |
| `smtp_password` | `str \| None` | `None` | SMTP authentication password |
| `use_starttls` | `bool` | `True` | Enable STARTTLS negotiation |
| `timeout` | `float` | `30.0` | Socket timeout in seconds |
| `raise_on_missing_attachments` | `bool` | `True` | Raise on missing attachment files |
| `raise_on_invalid_recipient` | `bool` | `True` | Raise on invalid recipient addresses |

### Attachment Security Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `attachment_allowed_extensions` | `frozenset[str] \| None` | `None` | Whitelist of allowed extensions |
| `attachment_blocked_extensions` | `frozenset[str] \| None` | `None` | Blacklist of blocked extensions |
| `attachment_allowed_directories` | `frozenset[Path] \| None` | `None` | Whitelist of allowed source directories |
| `attachment_blocked_directories` | `frozenset[Path] \| None` | `None` | Blacklist of blocked directories |
| `attachment_max_size_bytes` | `int \| None` | `26_214_400` | Maximum file size (25 MiB), `None` to disable |
| `attachment_allow_symlinks` | `bool` | `False` | Whether symlinks are permitted |
| `attachment_raise_on_security_violation` | `bool` | `True` | Raise or skip on security violation |

**Notes:**
- `None` values use `btx_lib_mail`'s OS-specific defaults (blocked extensions/directories)
- Empty arrays `[]` in TOML configuration are coerced to `None`
- `max_size_bytes = 0` is coerced to `None` (disable size checking)
- String paths are converted to `Path` objects during validation

### Configuration Loading

`load_email_config_from_dict()` handles the nested `[email.attachments]` TOML section:

```python
# TOML structure:
# [email]
# smtp_hosts = ["smtp.example.com:587"]
# [email.attachments]
# max_size_bytes = 10485760

config = load_email_config_from_dict(config_dict)
# Flattens to: attachment_max_size_bytes = 10485760
```

---

## Backup System

### Backup Flow

1. **Orchestrator** (`backup_all`) dispatches servers to `backup_server` via ThreadPoolExecutor
2. **Per-server** (`backup_server`) extracts settings, resolves SSH key, runs enabled backup types
3. **Config backup** (`backup_config`) streams tar archive via SSH pipe to local `.tar.gz`
4. **Package list** (`backup_packages`) captures `dpkg --get-selections` and `dpkg -l` to local `.txt` files
5. **ZFS backup** (`backup_zfs`) creates recursive snapshot, streams via `zfs send -R | gzip -1`
6. **Retention** (`apply_retention`) prunes old files per type, keeping N newest

### BackupSettings

Extracted from config via `extract_backup_settings()`:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `backup_base_dir` | `Path` | `/mnt/zpool-ssd/px-node-backups` | Base directory for backups |
| `max_parallel` | `int` | `4` | Concurrent backup threads |
| `zfs_retention_count` | `int` | `3` | Number of ZFS snapshots to keep per server |
| `config_retention_count` | `int` | `30` | Number of config backups to keep per server |
| `packagelist_retention_count` | `int` | `30` | Number of package list files to keep per server |
| `ssh_user` | `str` | `root` | SSH user for remote connections |
| `ssh_connect_timeout` | `int` | `15` | SSH connection timeout in seconds |
| `ssh_key_dir` | `str` | `/root/.ssh` | Directory for SSH keys |
| `ssh_key_prefix` | `str` | `backup_pull` | Key filename prefix |
| `bootstrap_key` | `str` | `""` | Bootstrap key for initial deployment |
| `authorized_keys_path` | `str` | `/etc/pve/priv/authorized_keys` | Remote authorized_keys path |
| `config_paths` | `list[str]` | `[]` | Paths to include in config backup |
| `exclude_patterns` | `list[str]` | `[]` | Patterns to exclude from config backup |

### Backup Storage Layout

```
{backup_base_dir}/
├── {server_name}/
│   ├── configs/
│   │   ├── backup_config_{server}_{timestamp}.tar.gz
│   │   ├── packages_selections_{server}_{timestamp}.txt
│   │   └── packages_list_{server}_{timestamp}.txt
│   └── snapshots/
│       └── {pool}_snapshot_{server}_{timestamp}.zfs.gz
```

---

## Testing Infrastructure

### In-Memory Adapters

The `adapters/memory/` package provides lightweight implementations for testing:

| Module | Protocols Satisfied |
|--------|---------------------|
| `memory/backup.py` | In-memory backup adapter (no-op) |
| `memory/config.py` | `GetConfig`, `GetDefaultConfigPath`, `DeployConfiguration`, `DisplayConfig` |
| `memory/email.py` | `SendEmail`, `SendNotification`, `LoadEmailConfigFromDict` |
| `memory/logging.py` | `InitLogging` |

Use `composition.build_testing()` to wire all in-memory adapters.

### Test Fixtures (conftest.py)

| Fixture | Purpose |
|---------|---------|
| `config_factory` | Creates real `Config` instances from test data |
| `source_info_factory` | Creates `SourceInfo` dicts for provenance-tracking tests |
| `inject_config` | Monkeypatches `get_config` to return a pre-built real `Config` |
| `email_cli_context` | Self-contained email testing: factory + spy bundled together |
| `cli_runner` | Fresh `CliRunner` per test |
| `clear_config_cache` | Clears `get_config` LRU cache before each test |
| `strip_ansi` | Strips ANSI escape sequences from CLI output |
| `managed_traceback_state` | Resets traceback flags to a known baseline and restores after test |

---

**Last Updated:** 2026-03-27 (v1.8.0 — packages backup, backup system documentation)
