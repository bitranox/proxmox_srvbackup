# Module Reference: Architecture & File Index

## Status

Describes the modules as they are in the source tree. Update it with every change that adds,
moves or removes a module, a CLI option or a public name.

---

## Related Files

### Domain Layer
- `src/proxmox_srvbackup/domain/behaviors.py`  -  Pure domain functions (greeting, timestamp, filename builders, summary formatting)
- `src/proxmox_srvbackup/domain/enums.py`  -  Type-safe enums (OutputFormat, DeployTarget, BackupType)
- `src/proxmox_srvbackup/domain/errors.py`  -  Domain exceptions (ConfigurationError, DeliveryError, InvalidRecipientError, BackupError, SSHConnectionError, SnapshotError, RetentionError)
- `src/proxmox_srvbackup/domain/models.py`  -  Value objects (ServerConfig, BackupResult, BackupSummary)

### Application Layer
- `src/proxmox_srvbackup/application/ports.py`  -  Callable Protocol definitions for adapter functions

### Adapters Layer
- `src/proxmox_srvbackup/adapters/backup/orchestrator.py`  -  Parallel backup execution across servers (BackupSettings, backup_all, backup_server)
- `src/proxmox_srvbackup/adapters/backup/config_backup.py`  -  Pull config tar archives from remote servers via SSH pipe
- `src/proxmox_srvbackup/adapters/backup/packages_backup.py`  -  Capture `dpkg --get-selections` and `dpkg -l` from each server
- `src/proxmox_srvbackup/adapters/backup/zfs_backup.py`  -  Pull ZFS rpool recursive snapshots via SSH pipe
- `src/proxmox_srvbackup/adapters/backup/retention.py`  -  Prune old backups (keep N newest matching a glob pattern)
- `src/proxmox_srvbackup/adapters/backup/setup_keys.py`  -  Generate/deploy per-server ed25519 SSH keys
- `src/proxmox_srvbackup/adapters/ssh/commands.py`  -  ssh_run, ssh_pipe_to_file, local_run, local_pipe_to_file
- `src/proxmox_srvbackup/adapters/config/loader.py`  -  Configuration loading with LRU caching
- `src/proxmox_srvbackup/adapters/config/deploy.py`  -  Configuration deployment
- `src/proxmox_srvbackup/adapters/config/display.py`  -  Configuration display (TOML/JSON output, redaction)
- `src/proxmox_srvbackup/adapters/config/overrides.py`  -  CLI `--set` override parsing and deep-merge
- `src/proxmox_srvbackup/adapters/email/config.py`  -  EmailConfig (a btx_lib_mail ConfMail), the `[email]` key mapping and `load_email_config_from_dict`
- `src/proxmox_srvbackup/adapters/email/transport.py`  -  `send_email` / `send_notification` over btx_lib_mail
- `src/proxmox_srvbackup/adapters/email/sender.py`  -  Re-exports of `config.py` and `transport.py`
- `src/proxmox_srvbackup/adapters/email/validation.py`  -  Email recipient validation
- `src/proxmox_srvbackup/adapters/logging/setup.py`  -  lib_log_rich initialization; takes only the `LOG_*` lines of a `.env`, and raises `InvalidLoggingConfigError` for a refused `[lib_log_rich]` value or `LOG_*` variable, after starting logging with its defaults (and without the `LOG_*` variables only when one of them is refused); `check_logging_config` refuses another configuration's logging settings through lib_log_rich's `validate_config`, without touching the running runtime
- `src/proxmox_srvbackup/adapters/cli/`  -  CLI adapter package:
  - `__init__.py`  -  Public facade
  - `constants.py`  -  Shared constants
  - `safe_console.py`  -  Encode-safe terminal output; use `safe_console.echo` instead of `click.echo`
  - `exit_codes.py`  -  POSIX exit codes (ExitCode IntEnum)
  - `context.py`  -  Click context helpers
  - `config_load.py`  -  Configuration load for the CLI; records a load failure, `require_config` refuses with exit 78, `check_logging` checks the logging settings of a configuration reloaded by `config --profile`, refusing them as the root does; `load_config` loads with profile, `.env` and `--set`, and `start_logging` starts logging for the root group, recording a refused `[lib_log_rich]` value or `LOG_*` variable like a load failure
  - `root.py`  -  Root command group
  - `main.py`  -  Entry point (accepts `services_factory`)
  - `typed_click.py`  -  Strictly typed wrappers for rich_click's `option`, `version_option` and `get_current_context`
  - `commands/backup.py`  -  backup, setup-keys commands
  - `commands/info.py`  -  info, hello, fail commands
  - `commands/config.py`  -  config, config-deploy, config-generate-examples commands
  - `commands/email/`  -  Email commands package:
    - `__init__.py`  -  Public exports
    - `_common.py`  -  Shared SMTP override options and their typed `EmailConfigOverrides`, config
      loading and error-to-exit-code mapping
    - `send_email.py`  -  send-email command
    - `send_notification.py`  -  send-notification command
  - `commands/logging.py`  -  logdemo command

### Adapters Layer (In-Memory / Testing)
- `src/proxmox_srvbackup/adapters/memory/__init__.py`  -  Public facade + Protocol conformance assertions
- `src/proxmox_srvbackup/adapters/memory/backup.py`  -  In-memory backup adapters (no-op)
- `src/proxmox_srvbackup/adapters/memory/config.py`  -  In-memory config adapters
- `src/proxmox_srvbackup/adapters/memory/email.py`  -  In-memory email adapters
- `src/proxmox_srvbackup/adapters/memory/logging.py`  -  In-memory logging (a quiet lib_log_rich runtime for tests)

### Composition Layer
- `src/proxmox_srvbackup/composition/__init__.py`  -  Wires adapters to ports (`build_production`, `build_testing`)

### Entry Points
- `src/proxmox_srvbackup/entry.py`  -  Console-script entry point; wires production services before invoking the CLI
- `src/proxmox_srvbackup/__main__.py`  -  Thin shim for `python -m`
- `src/proxmox_srvbackup/__init__.py`  -  Public API exports
- `src/proxmox_srvbackup/__init__conf__.py`  -  Package metadata constants

### Configuration Defaults
- `src/proxmox_srvbackup/adapters/config/defaultconfig.toml`  -  Base defaults
- `src/proxmox_srvbackup/adapters/config/defaultconfig.d/40-layered-config.toml`  -  lib_layered_config integration docs
- `src/proxmox_srvbackup/adapters/config/defaultconfig.d/50-mail.toml`  -  Email defaults
- `src/proxmox_srvbackup/adapters/config/defaultconfig.d/60-backup.toml`  -  Backup configuration and server definitions
- `src/proxmox_srvbackup/adapters/config/defaultconfig.d/90-logging.toml`  -  Logging defaults
- `src/proxmox_srvbackup/adapters/config/systemd/`  -  Systemd timer/service units for automated backups

### Tests
- `tests/conftest.py`  -  Shared fixtures (see Test Fixtures below)
- `tests/test_backup_adapters.py`  -  Backup adapter pure-logic tests (retention, tar command, SSH command, key path, orchestrator)
- `tests/test_backup_per_server.py`  -  Per-server backup type control (_as_bool, _servers_from_config, skip semantics, dry-run)
- `tests/test_behaviors.py`  -  Domain function tests (greeting, timestamp, filename builders, summary formatting)
- `tests/test_cache_effectiveness.py`  -  Configuration loading returns consistent (cached) results
- `tests/test_cli_attachment_refused.py`  -  An attachment btx_lib_mail's security checks refuse exits 77 with one `Error:` line, nothing delivered
- `tests/test_cli_config.py`  -  `config`, `config-deploy`, `config-generate-examples` commands
- `tests/test_cli_config_errors.py`  -  A configuration that cannot be loaded: who reports it, and who still runs
- `tests/test_cli_core.py`  -  Traceback, main entry, help, hello, fail, info, unknown command
- `tests/test_cli_email.py`  -  `send-email`, `send-notification`, SMTP and credential overrides
- `tests/test_cli_email_config_errors.py`  -  An invalid `[email]` section or option value: one `Error:` line per problem
- `tests/test_cli_env_file.py`  -  `--env-file` path passing, validation and value override
- `tests/test_cli_exit_codes.py`  -  Exit codes through the CLI
- `tests/test_cli_main_exit.py`  -  Exit codes and stderr through the real `main()` entry point
- `tests/test_cli_overrides.py`  -  `--set` through the CLI
- `tests/test_cli_validation.py`  -  Profile name validation
- `tests/test_config_overrides.py`  -  `--set` parsing tests
- `tests/test_declared_dependencies.py`  -  Every third-party module imported at run time is a declared dependency
- `tests/test_deploy_mode_safety.py`  -  `--dir-mode`/`--file-mode` literal, range and safety checks
- `tests/test_deploy_permissions.py`  -  `config-deploy` permission options
- `tests/test_display.py`  -  Config display formatting tests
- `tests/test_email_attachment_lists.py`  -  A list-typed email setting in an unreadable form is refused, never dropped
- `tests/test_email_library_limits.py`  -  What btx_lib_mail refuses for this tool: recipient and attachment counts, default blocked extensions, SMTP port syntax
- `tests/test_email_config_translation.py`  -  The `[email]` section becomes an EmailConfig: file keys kept, unknown keys refused
- `tests/test_email_password_secrecy.py`  -  The SMTP password never reaches an error message, the console or the log
- `tests/test_email_shipped_defaults.py`  -  The shipped `[email]` defaults keep the library's attachment protection on
- `tests/test_enums.py`  -  Domain enum tests
- `tests/test_errors.py`  -  Domain error types
- `tests/test_logging.py`  -  Logging configuration model
- `tests/test_logging_documented_examples.py`  -  Every `[lib_log_rich]` environment and `.env` example in `90-logging.toml` and `.env.example` is a value logging accepts
- `tests/test_logging_dotenv_isolation.py`  -  Only `LOG_*` lines of a `.env` reach the environment; an invalid `[lib_log_rich]` section or `LOG_*` variable is a configuration failure that leaves logging running
- `tests/test_mail.py`  -  Email configuration and sending tests (the `integration` ones send real mail)
- `tests/test_memory_logging.py`  -  Testing-composition logging runtime and the per-test logging reset
- `tests/test_metadata.py`  -  Package metadata and PEP 561 marker tests
- `tests/test_metadata_sync.py`  -  `__init__conf__` constants stay in sync with `pyproject.toml`
- `tests/test_module_entry.py`  -  `python -m` entry tests
- `tests/test_module_reference_sync.py`  -  The EmailConfig field table in this document matches the model
- `tests/test_packages_backup.py`  -  Package list backup adapter tests (filename, dpkg output, retention, dry-run, local/remote)
- `tests/test_permission_defaults.py`  -  `config-deploy` hands permissions to lib_layered_config: `--set` overrides, `.env` and deployed destinations never decide a mode, refusals exit 78
- `tests/test_ports.py`  -  Protocol conformance tests
- `tests/test_property_email.py`  -  Property-based EmailConfig tests
- `tests/test_property_overrides.py`  -  Property-based `--set` override tests
- `tests/test_safe_console.py`  -  Legacy-codepage output tests, plus the guard forbidding direct `click.echo`
- `tests/test_ssh_commands.py`  -  SSH/local command unit tests (mocked subprocess)
- `tests/test_summary_report.py`  -  Summary report and subject formatting tests

---

## Architecture

### Layer Assignments

| Directory/Module       | Layer       | Responsibility                                                             |
|------------------------|-------------|----------------------------------------------------------------------------|
| `domain/`              | Domain      | Pure logic  -  no I/O, logging, or frameworks                              |
| `application/ports.py` | Application | Protocol definitions for adapters                                          |
| `adapters/backup/`     | Adapters    | Backup orchestration, config/ZFS/packages backup, retention, SSH key setup |
| `adapters/ssh/`        | Adapters    | SSH command execution and file streaming                                   |
| `adapters/config/`     | Adapters    | Configuration loading, deployment, display                                 |
| `adapters/email/`      | Adapters    | SMTP email sending                                                         |
| `adapters/logging/`    | Adapters    | lib_log_rich initialization                                                |
| `adapters/cli/`        | Adapters    | Click CLI framework integration                                            |
| `adapters/memory/`     | Adapters    | In-memory implementations for testing                                      |
| `composition/`         | Composition | Wires adapters to ports                                                    |

### Import Enforcement

Layer boundaries enforced via `import-linter` contracts in `pyproject.toml`:
- **Domain is pure**: Cannot import from adapters or composition
- **Clean Architecture layers**: Validates dependency direction (composition -> adapters -> application -> domain)

Run `lint-imports` to verify compliance.

---

## Exit Codes

POSIX-conventional exit codes defined in `adapters/cli/exit_codes.py`:

| Code | Name                 | Usage                                                                                                                  |
|------|----------------------|------------------------------------------------------------------------------------------------------------------------|
| 0    | `SUCCESS`            | Command completed successfully                                                                                         |
| 1    | `GENERAL_ERROR`      | Unhandled exception, general failure                                                                                   |
| 2    | `FILE_NOT_FOUND`     | Attachment or file not found; also click's usage error (bad option value, malformed `--set`, invalid `--profile` name) |
| 13   | `PERMISSION_DENIED`  | Cannot write to target directory                                                                                       |
| 22   | `INVALID_ARGUMENT`   | Invalid CLI argument or section not found                                                                              |
| 69   | `SMTP_FAILURE`       | SMTP delivery failed                                                                                                   |
| 77   | `ATTACHMENT_REFUSED` | Attachment refused by btx_lib_mail's security checks (blocked extension or directory, symlink, size, ...)              |
| 78   | `CONFIG_ERROR`       | Configuration missing, not loadable or invalid                                                                         |
| 110  | `TIMEOUT`            | Operation timed out                                                                                                    |
| 130  | `SIGNAL_INT`         | Interrupted (SIGINT/Ctrl+C)                                                                                            |
| 141  | `BROKEN_PIPE`        | Output pipe closed                                                                                                     |
| 143  | `SIGNAL_TERM`        | Terminated (SIGTERM)                                                                                                   |

---

## CLI Commands

### Root Command

**Command:** `proxmox-srvbackup`

| Option                         | Description                                 |
|--------------------------------|---------------------------------------------|
| `--version`                    | Show version and exit                       |
| `--traceback / --no-traceback` | Show full Python traceback on errors        |
| `--profile NAME`               | Load configuration from a named profile     |
| `--set SECTION.KEY=VALUE`      | Override configuration setting (repeatable) |
| `--env-file PATH`              | Explicit `.env` file path                   |
| `-h, --help`                   | Show help and exit                          |

### backup

Pull backups from all configured Proxmox servers.

| Option                      | Description                                         |
|-----------------------------|-----------------------------------------------------|
| `--server NAME`             | Backup only this server (by name from config)       |
| `--type [all\|config\|zfs]` | Backup type filter (default: all)                   |
| `--dry-run`                 | Show what would be executed without running backups |

**Exit codes:** 0, 1, 2 (usage error, including an invalid `--profile` name or conflicting `--set`), 22 (server not found), 78 (configuration not loadable)

### setup-keys

Generate per-server ed25519 keypairs and deploy public keys to remote servers.

**Exit codes:** 0, 1, 2 (usage error), 78 (configuration not loadable)

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

| Option                   | Description                    |
|--------------------------|--------------------------------|
| `--format [human\|json]` | Output format (default: human) |
| `--section NAME`         | Show only specific section     |
| `--profile NAME`         | Override the root's profile    |

**Exit codes:** 0, 2 (usage error), 22 (section not found), 78 (configuration not loadable)

### config-deploy

Deploy default configuration to system or user directories.

| Option                             | Description                                                      |
|------------------------------------|------------------------------------------------------------------|
| `--target [app\|host\|user]`       | Target layer(s)  -  required, repeatable                         |
| `--force`                          | Replace differing files, keeping the old one as `<name>.bak`     |
| `--profile NAME`                   | Deploy to profile subdirectory                                   |
| `--permissions / --no-permissions` | Set Unix permissions (default: `enabled` from the configuration) |
| `--dir-mode MODE`                  | Directory mode for every target (octal)                          |
| `--file-mode MODE`                 | File mode for every target (octal)                               |

**Exit codes:** 0, 1, 2 (usage error, including a refused `--dir-mode`/`--file-mode` or `--profile` name, and `--no-permissions` together with a mode), 13 (permission denied), 78 (lib_layered_config refused the permission settings: a configured one, which both `--dir-mode` and `--file-mode` or `--no-permissions` deploy past, or a `--set` of `lib_layered_config.default_permissions`)

### config-generate-examples

Generate example configuration files.

| Option              | Description                   |
|---------------------|-------------------------------|
| `--destination DIR` | Target directory  -  required |
| `--force`           | Overwrite existing files      |

**Exit codes:** 0, 1

### send-email

Send email using configured SMTP settings.

| Option                                                               | Description                          |
|----------------------------------------------------------------------|--------------------------------------|
| `--to ADDRESS`                                                       | Recipient (repeatable)               |
| `--subject TEXT`                                                     | Subject line  -  required            |
| `--body TEXT`                                                        | Plain-text body                      |
| `--body-html TEXT`                                                   | HTML body                            |
| `--from ADDRESS`                                                     | Override sender                      |
| `--attachment PATH`                                                  | File to attach (repeatable)          |
| `--smtp-host HOST:PORT`                                              | Override SMTP host (repeatable)      |
| `--smtp-username USER`                                               | Override username                    |
| `--smtp-password PASS`                                               | Override password                    |
| `--use-starttls / --no-use-starttls`                                 | Override STARTTLS                    |
| `--timeout SECONDS`                                                  | Override timeout                     |
| `--raise-on-missing-attachments / --no-raise-on-missing-attachments` | Override missing-attachment handling |
| `--raise-on-invalid-recipient / --no-raise-on-invalid-recipient`     | Override invalid-recipient handling  |

**Exit codes:** 0, 2 (file not found, or usage error), 22 (invalid option value), 69 (SMTP failure), 77 (an attachment refused by btx_lib_mail's security checks), 78 (no SMTP hosts, an invalid `[email]` section, or configuration not loadable)

### send-notification

Send simple plain-text notification email.

| Option                                                           | Description                         |
|------------------------------------------------------------------|-------------------------------------|
| `--to ADDRESS`                                                   | Recipient (repeatable)              |
| `--subject TEXT`                                                 | Subject  -  required                |
| `--message TEXT`                                                 | Message  -  required                |
| `--from ADDRESS`                                                 | Override sender                     |
| `--smtp-host HOST:PORT`                                          | Override SMTP host (repeatable)     |
| `--smtp-username USER`                                           | Override username                   |
| `--smtp-password PASS`                                           | Override password                   |
| `--use-starttls / --no-use-starttls`                             | Override STARTTLS                   |
| `--timeout SECONDS`                                              | Override timeout                    |
| `--raise-on-invalid-recipient / --no-raise-on-invalid-recipient` | Override invalid-recipient handling |

**Exit codes:** 0, 2 (usage error), 22 (invalid option value), 69 (SMTP failure), 78 (no SMTP hosts, an invalid `[email]` section, or configuration not loadable)

### logdemo

Run logging demonstration.

| Option         | Description                      |
|----------------|----------------------------------|
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

| Parameter    | Type          | Default  | Description                                 |
|--------------|---------------|----------|---------------------------------------------|
| `profile`    | `str`         | required | Profile name to validate                    |
| `max_length` | `int \| None` | 64       | Maximum length (DEFAULT_MAX_PROFILE_LENGTH) |

### Validation Rules

| Rule             | Description                                          |
|------------------|------------------------------------------------------|
| Maximum length   | 64 characters (configurable via `max_length`)        |
| Character set    | ASCII alphanumeric, hyphens (`-`), underscores (`_`) |
| Start character  | Must start with alphanumeric character               |
| Empty string     | Rejected                                             |
| Windows reserved | CON, PRN, AUX, NUL, COM1-9, LPT1-9 rejected          |
| Path traversal   | `/`, `\`, `..` rejected                              |
| Control chars    | Rejected                                             |

### Error Handling

Raises `ValueError` with descriptive message on invalid input.

---

## Email Configuration

### EmailConfig Fields

`EmailConfig` (`adapters/email/config.py`, re-exported by `adapters/email/sender.py`) subclasses
btx_lib_mail's `ConfMail`: frozen, a name that is not a field is refused, the password is a
`SecretStr`, and a validation error never shows the password or a host. It adds `from_address` and
`recipients`. ConfMail checks every SMTP host's syntax (port range, IPv6 brackets, host name
labels) when it loads, so `EmailConfig` has no host check of its own. In Python the fields use
the library's names; the configuration file keeps its own keys (fourth column).

| Field                          | Type                | Default | File key (`[email]`)           | Description                                                      |
|--------------------------------|---------------------|---------|--------------------------------|------------------------------------------------------------------|
| `smtphosts`                    | `list[str]`         | `[]`    | `smtp_hosts`                   | SMTP servers in `host[:port]` format                             |
| `from_address`                 | `str \| None`       | `None`  | `from_address`                 | Default sender address                                           |
| `recipients`                   | `list[str]`         | `[]`    | `recipients`                   | Default recipient addresses                                      |
| `smtp_username`                | `str \| None`       | `None`  | `smtp_username`                | SMTP authentication username; an integer is read as its digits   |
| `smtp_password`                | `SecretStr \| None` | `None`  | `smtp_password`                | SMTP authentication password; unwrap with `.get_secret_value()`  |
| `smtp_use_starttls`            | `bool`              | `True`  | `use_starttls`                 | Enable STARTTLS negotiation                                      |
| `smtp_starttls_verify`         | `bool`              | `True`  | `starttls_verify`              | Verify the server certificate after STARTTLS                     |
| `smtp_timeout`                 | `float`             | `30.0`  | `timeout`                      | Socket timeout in seconds                                        |
| `smtp_local_hostname`          | `str \| None`       | `None`  | `local_hostname`               | Host name announced in EHLO; `None` looks it up once per process |
| `smtp_delivery_deadline`       | `float \| None`     | `None`  | `delivery_deadline`            | Upper bound in seconds for one SMTP session; `None` for none     |
| `recipient_max_count`          | `int \| None`       | `1000`  | `recipient_max_count`          | Most recipients one send accepts; `None` lifts the limit         |
| `raise_on_missing_attachments` | `bool`              | `True`  | `raise_on_missing_attachments` | Raise on missing attachment files                                |
| `raise_on_invalid_recipient`   | `bool`              | `True`  | `raise_on_invalid_recipient`   | Raise on invalid recipient addresses                             |

### Attachment Security Fields

| Field                                    | Type                      | Default      | File key (`[email.attachments]`) | Description                                             |
|------------------------------------------|---------------------------|--------------|----------------------------------|---------------------------------------------------------|
| `attachment_allowed_extensions`          | `frozenset[str] \| None`  | `None`       | `allowed_extensions`             | Whitelist of allowed extensions                         |
| `attachment_blocked_extensions`          | `frozenset[str]`          | POSIX + Win  | `blocked_extensions`             | Blacklist of blocked extensions (both lists, every OS)  |
| `attachment_allowed_directories`         | `frozenset[Path] \| None` | `None`       | `allowed_directories`            | Whitelist of allowed source directories                 |
| `attachment_blocked_directories`         | `frozenset[Path]`         | OS defaults  | `blocked_directories`            | Blacklist of blocked directories                        |
| `attachment_max_size_bytes`              | `int \| None`             | `26_214_400` | `max_size_bytes`                 | Maximum file size (25 MiB), `None` to disable           |
| `attachment_max_count`                   | `int \| None`             | `100`        | `max_count`                      | Most attachments one send accepts, `None` to disable    |
| `attachment_allow_symlinks`              | `bool`                    | `False`      | `allow_symlinks`                 | Whether symlinks are permitted                          |
| `attachment_raise_on_security_violation` | `bool`                    | `True`       | `raise_on_security_violation`    | Raise or skip on security violation                     |
| `attachment_allow_empty_blocklists`      | `bool`                    | `False`      | not exposed                      | Allow an empty blocked set (blocks nothing) from Python |

### Configuration Loading

lib_layered_config is the only reader of configuration: it merges every layer (the shipped
defaults, the app, host and user files, `.env`, the environment, `--set`) into one mapping.
`load_email_config_from_dict()` turns that mapping's `[email]` section into an `EmailConfig`:

- the six keys in the fourth column that differ from the field names are mapped;
- `[email.attachments]` keys become `attachment_<key>`;
- a key that is not listed is refused (exit 78, `email.<key>: unknown key`), whatever layer it came from;
- blank text means "not configured"; a single host or address string is a one-entry list;
- an empty attachment list (`[]` or a blank string) means the library's defaults, and any other
  value that is not a list, such as a comma-separated string, is refused, as is a blank entry;
- a limit of 0 (`max_size_bytes`, `max_count`, `recipient_max_count`, `delivery_deadline`) means no limit.

`describe_validation_error()` renders a refusal as one `email.<file key>: <reason>` line per
problem, never with the refused value.

`adapters/email/config.py` also exports the key tables the loader works from:

| Name                | Content                                                                      |
|---------------------|------------------------------------------------------------------------------|
| `SECTION_KEYS`      | Every key `[email]` accepts (the `attachments` table included)               |
| `ATTACHMENT_KEYS`   | Every key `[email.attachments]` accepts; each names field `attachment_<key>` |
| `FILE_KEY_TO_FIELD` | File key -> `EmailConfig` field, for the six keys whose names differ         |

---

## Configuration Overrides

`adapters/config/overrides.py` parses and applies `--set SECTION.KEY=VALUE`. Public names
(`__all__`):

| Name              | Kind     | Purpose                                                                                 |
|-------------------|----------|-----------------------------------------------------------------------------------------|
| `parse_override`  | function | Split one `SECTION.KEY[.SUBKEY...]=VALUE` string into a `ConfigOverride`                |
| `coerce_value`    | function | Read a raw value as JSON (bool, number, null, array, object), falling back to the text  |
| `nest_overrides`  | function | Parse all `--set` values into the nested mapping they override, refusing contradictions |
| `apply_overrides` | function | Deep-merge the overrides into a `Config`, recording their provenance as `CLI_LAYER`     |
| `ConfigOverride`  | class    | One parsed override: section, key path and value                                        |
| `CoercedValue`    | type     | Union of the types `coerce_value` can return                                            |
| `CLI_LAYER`       | constant | Provenance layer name (`"cli"`) for a value that came from `--set`                      |

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

| Field                         | Type        | Default                          | Description                                     |
|-------------------------------|-------------|----------------------------------|-------------------------------------------------|
| `backup_base_dir`             | `Path`      | `/mnt/zpool-ssd/px-node-backups` | Base directory for backups                      |
| `max_parallel`                | `int`       | `4`                              | Concurrent backup threads                       |
| `zfs_retention_count`         | `int`       | `3`                              | Number of ZFS snapshots to keep per server      |
| `config_retention_count`      | `int`       | `30`                             | Number of config backups to keep per server     |
| `packagelist_retention_count` | `int`       | `30`                             | Number of package list files to keep per server |
| `ssh_user`                    | `str`       | `root`                           | SSH user for remote connections                 |
| `ssh_connect_timeout`         | `int`       | `15`                             | SSH connection timeout in seconds               |
| `ssh_key_dir`                 | `str`       | `/root/.ssh`                     | Directory for SSH keys                          |
| `ssh_key_prefix`              | `str`       | `backup_pull`                    | Key filename prefix                             |
| `bootstrap_key`               | `str`       | `""`                             | Bootstrap key for initial deployment            |
| `authorized_keys_path`        | `str`       | `/etc/pve/priv/authorized_keys`  | Remote authorized_keys path                     |
| `config_paths`                | `list[str]` | `[]`                             | Paths to include in config backup               |
| `exclude_patterns`            | `list[str]` | `[]`                             | Patterns to exclude from config backup          |

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

| Module              | Protocols Satisfied                                                         |
|---------------------|-----------------------------------------------------------------------------|
| `memory/backup.py`  | In-memory backup adapters (no-op)                                           |
| `memory/config.py`  | `GetConfig`, `GetDefaultConfigPath`, `DeployConfiguration`, `DisplayConfig` |
| `memory/email.py`   | `SendEmail`, `SendNotification`                                             |
| `memory/logging.py` | `InitLogging`, `CheckLoggingConfig`                                         |

`adapters/memory` exports `EmailSpy` (from `memory/email.py`): its `send_email` and
`send_notification` methods satisfy the email ports and record each call as a `CapturedEmail` /
`CapturedNotification` in `sent_emails` / `sent_notifications`; `should_fail` makes them return
False and `raise_exception` makes them raise. Create one spy per test.

Use `composition.build_testing()` to wire all in-memory adapters. It wires the real
`load_email_config_from_dict`, so CLI tests run through the same translation as production.

### Test Fixtures (conftest.py)

| Fixture                   | Purpose                                                                                                                                                                 |
|---------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `config_factory`          | Creates real `Config` instances from test data                                                                                                                          |
| `source_info_factory`     | Creates `SourceInfo` dicts for provenance-tracking tests                                                                                                                |
| `inject_config`           | Injects config into CLI path                                                                                                                                            |
| `email_cli_context`       | Self-contained email testing: factory + spy bundled together                                                                                                            |
| `cli_runner`              | Fresh `CliRunner` per test                                                                                                                                              |
| `strip_ansi`              | Strips ANSI escape codes from output                                                                                                                                    |
| `clear_config_cache`      | Clears LRU cache before tests                                                                                                                                           |
| `managed_traceback_state` | Resets/restores traceback configuration                                                                                                                                 |
| `isolated_logging_state`  | Autouse: after every test, shuts the lib_log_rich runtime down and restores the root logger; yields that restore step                                                   |
| `user_layer_in_tmp_path`  | Points every OS's user-layer location (`HOME`, `USERPROFILE`, `XDG_CONFIG_HOME`, `APPDATA`, `LOCALAPPDATA`) at `tmp_path` and returns it, so a real deploy writes there |

---

**Last Updated:** 2026-10-08 (`send-notification` options, test fixtures)
