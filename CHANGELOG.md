# Changelog

All notable changes to this project will be documented in this file following
the [Keep a Changelog](https://keepachangelog.com/) format.


## [Unreleased]

### Fixed
- **`email.smtp_hosts` and `email.recipients` set to nothing mean not configured.** A bare YAML
  key or an environment `null` was refused as "Input should be a valid list" for both settings.
  Both now read `None` as an empty list.
- **`build_testing()` can run a command, and tests no longer pass or fail by order.** The
  in-memory logging initializer was a no-op while every command binds job context onto the
  lib_log_rich runtime, so any command under the testing composition raised
  `RuntimeError('lib_log_rich.init() must be called before using the logging API')`. It now
  starts a quiet runtime (no journald, event log, Graylog or queue; console at ERROR; no `.env`
  loading). An autouse fixture shuts the runtime down and restores the root logger after every
  test, the conftest fixtures that build services use the quiet runtime instead of the production
  one (whose queued INFO lines raced into CliRunner's stderr), and CLI output is rendered
  uncoloured at a fixed 120 columns, so CI (`GITHUB_ACTIONS`, 79-column Windows runners) and a
  developer machine see the same text.
- **No more `SystemExit: N` on stderr.** `backup`, `setup-keys`, the email commands and the config
  commands raised a bare `SystemExit`, which `main()`'s catch-all branch printed as
  `SystemExit: 1` (or `78`, `69`, ...) after the real error message, so a failed backup run under
  systemd logged what reads like a crash. They now exit through click's context (`ctx.exit`), and
  `main()` returns the exit code rich_click hands back instead of discarding it. `typed_click`
  gains a typed `get_current_context` wrapper for the helpers that have no `ctx` parameter.
- **A failed send is reported once.** click's `Exit` subclasses `RuntimeError`, so the send-result
  exit raised inside the delivery `try` was caught again by the `DeliveryError`/`RuntimeError`
  branch, adding "SMTP delivery failed" / "Failed to send email" to the correct "sending failed".
  The send result is handled in the `try`'s `else`, and `config-deploy` re-raises an `Exit` before
  its catch-all, so a deliberate exit keeps its own code instead of becoming 1.
- **A broken configuration file no longer disables every command.** The root group loaded the
  configuration before any subcommand option was parsed and let a load error escape, so a
  malformed `config.toml` made every command, `--help` and `config-deploy` (the command that
  replaces the file) fail with exit 1 and empty stdout. The root now records the failure
  (`adapters/cli/config_load.py`); `backup`, `setup-keys`, `config`, `send-email` and
  `send-notification` refuse with exit 78 and one line naming it, while
  `config-generate-examples`, `info`, `hello`, `logdemo` and help still run. `config-deploy` runs
  too, with the default permissions, and warns which configuration it could not read, so
  `config-deploy --force` replaces the broken file. An unreadable file (exit 13 before) takes the
  same path, and so does an `--env-file` that is not UTF-8 (the line names the file).
  `--traceback` prints the loader's chained traceback before the line. What the command line gets
  wrong is checked BEFORE loading, so a broken file cannot hide it: a malformed `--set` or an
  invalid `--profile` name is a usage error (exit 2) for every command, `info` and `hello`
  included (see Changed). So are two `--set` values that give one key a value and put a key under
  it (`--set a.b=1 --set a.b.c=2`), which escaped as a `TypeError` (exit 22) in one order and
  silently dropped the earlier value in the other; give a whole table in one `--set`. Any other
  exception from the loader is a bug and propagates as one. `config --profile X` reloads with the
  root's `--env-file` instead of searching for another `.env`.
- **`[lib_layered_config.default_permissions]` now takes effect, and only the configuration
  files decide it.** The per-layer modes were read, but only `enabled` was ever used, so
  `--set lib_layered_config.default_permissions.user_directory='"0o750"'` still produced a `0o700`
  directory, and a malformed mode fell back to the default silently. `config-deploy` now hands its
  options and any `--set` of the section to lib_layered_config, which deploys each target with its
  configured directory and file mode (`--dir-mode`/`--file-mode` still win) and reads the section
  itself: from the bundled defaults, the configuration files the deploy does not overwrite and the
  environment, never from `.env` (nor `--env-file`). So a `.env` in the working directory can
  neither change a deployed mode nor block a deploy, and `config-deploy --force` replaces a
  deployed file that does not parse or holds a bad value without further options (the warning
  about a configuration that did not load is gone: the deploy no longer reads it). A malformed or
  out-of-range mode, a bare integer (TOML `user_file = 400` is decimal 400, i.e. `0o620`), an
  unsafe mode, a non-boolean `enabled`, a section that is not a table or an unknown key stops the
  command with exit 78 before anything is written: one `Error:` line per problem naming the key
  and where it was set (`(source: override)` for a `--set`), then, for a configured value, a hint
  that both `--dir-mode` and `--file-mode` deploy anyway. `--no-permissions` together with
  `--dir-mode` or `--file-mode` is a usage error (exit 2). "Deployed configuration" is logged
  after the deploy, not before it.
- **An invalid `[email]` section is a configuration error.** `send-email` and `send-notification`
  let the `ValidationError` escape to `main()`'s catch-all, which exited 22 with pydantic's
  multi-line report and documentation URL. They now exit 78 with one line per problem,
  `Error: Invalid configuration: email.<key>: <reason>` (an `[email.attachments]` setting is
  named by its nested key), and the refused value is never printed. An invalid option value
  (`--timeout -5`) still exits 22, now in the same one-line form (`Error: Invalid option value:
  ...`).

### Changed
- **Exit code change: a configuration that does not load exits 78, an invalid `--profile` name
  exits 2.** A broken `config.toml` made every command exit 1 and an unreadable one exit 13;
  `backup`, `setup-keys`, `config`, `send-email` and `send-notification` now exit 78 (EX_CONFIG)
  for both, and the other commands run. An invalid `--profile` name such as `../x` exited 22 from
  every command; it is now a usage error, exit 2, for the root's `--profile`, `config --profile`
  and `config-deploy --profile` alike (`config-deploy --profile ../x` used to fail inside the
  deploy). Conflicting `--set` values also exit 2 (was 22). A monitoring script that tells a
  failed backup run from a broken configuration by exit code has to test for 78.
- **Requires lib_layered_config 7.0.1.** An unquoted `.env` value now converts like the
  environment layer: `true`/`false` arrive as booleans, `null`/`none` as None (not for a secret
  key such as a password), a JSON array or object parsed, a number that converts back to the same
  text as a number, anything else as text; quote a value to keep it text. So
  `EMAIL__USE_STARTTLS=false` in a `.env` reads as the boolean it says.
- **`config-deploy` leaves every permission decision to lib_layered_config's `deploy_config`**
  (see Fixed). The deploy port (`DeployConfiguration`) takes `set_permissions: bool | None`
  (None, the default, follows the configured `enabled`) and `permission_overrides`. Refusals of
  `--dir-mode`/`--file-mode` use the library's wording ("unsafe directory mode 0o777: group
  write (0o020); world write (0o002)"), and a zero-padded mode such as `0000750` is accepted as
  `0o750`.
- **Exit code change: an invalid `[email]` section exits 78, no longer 22** (see Fixed). A script
  that checks for 22 after `send-email` or `send-notification` must check for 78 (EX_CONFIG); an
  invalid option value such as `--timeout -5` still exits 22. The log record for a refused
  option names its problems in a `problems` field instead of the pydantic dump in `error`.
  `describe_validation_error` in `adapters/email/config.py` is public.

### Removed
- `adapters.config.permissions` as a whole: `parse_mode` (whose silent fall-back to the default
  was the bug), `get_permission_defaults`, `get_modes_for_target` and the `PermissionDefaults`
  model. lib_layered_config reads and validates the section now; a caller that wants the
  settings uses its `deploy_permissions_from_config`.

### Security
- An email attachment allow or block list given in a form it cannot be read in is now refused instead of silently ignored. A comma-separated value (`.pdf,.txt` in an environment variable or `.env`) arrives as one string, and the validators turned any value that was not a list into "not configured", so btx_lib_mail's default lists applied in place of the configured ones. A list or tuple is read as its items (an empty one still means not configured), a set is kept as given, an empty value means not configured, and anything else fails validation naming the setting and the accepted form (a JSON array such as `[".pdf", ".txt"]`). `smtp_hosts` and `recipients` no longer turn a tuple or another non-list value into an empty list. The shipped `50-mail.toml` and `.env.example` documented the comma form for all six list settings; they now show the JSON-array and per-index forms.
- **`config-deploy` refuses unsafe and malformed modes (exit code change: 2, nothing written).**
  `--dir-mode -1` chmodded the config directory to `0o7777` (setuid, sticky, world-writable), a
  20-digit value raised `OverflowError`, and `--dir-mode 777` or `--file-mode 666` deployed
  world-writable configuration, including the file that holds the SMTP password. `--dir-mode`/`--file-mode` and every configured mode now accept
  only a plain octal literal in `0`..`0o7777`, and refuse the setuid/setgid/sticky bits, group
  and world write (on macOS every local account shares the group `staff`), an execute bit on a
  file, a directory without owner `rwx` and a file without owner `rw`, naming each offending bit.
  A configured mode given as a bare integer is refused instead of being read as DECIMAL.
  Migration: quote configured modes (`user_file = "640"`), and use the `0o` prefix in environment
  variables and `--set`; `--dir-mode 770` and `--file-mode 660` are refused.

## [1.9.5] 2026-07-24

### Fixed
- CI lint gate is green again under the latest `ruff`. A newer `ruff` began enforcing `PLR0917` (too many positional arguments) on the CLI command callbacks and helpers, turning the scheduled CI red. The callbacks now take keyword-only parameters after `ctx` (Click already invokes them by keyword), and `_execute_deploy` is keyword-only after its first argument, so the rule passes without loosening it.

### Changed
- Removed the blanket `[tool.ruff.lint].ignore` list (`RUF002`, `RUF022`, `PLC0415`, `TC001`, `TC002`, `TC003`, `TC006`) and fixed each violation at the source instead of suppressing it: sorted `__all__` and type-checking imports via autofix, replaced ambiguous en-dashes with ASCII hyphens in docstrings, and moved trivial deferred imports to module top while keeping the genuinely lazy ones with a rule-specific `# noqa: PLC0415` and a reason.
- Added `[tool.ruff.lint.flake8-type-checking].runtime-evaluated-base-classes = ["pydantic.BaseModel"]` so Pydantic models keep their field-annotation imports at runtime.
- `PLC0415` is now ignored only for `tests/*.py`, where deferred imports inside test bodies are a deliberate idiom for exercising import and cache behaviour.
- Doctests that construct domain models or enums now import those names inside the example, keeping them runnable after the type-only imports moved under `TYPE_CHECKING`.

## [1.9.4] 2026-07-20

### Fixed
- `config-deploy` now prints an ASCII marker for each written file. A non-ASCII glyph raised `UnicodeEncodeError` on a legacy Windows console codepage (cp1252) after the files were already written, so the command exited 1 and misreported a deploy that had actually succeeded.
- Invalid `--profile` values raise `ValueError` again. Newer `lib_layered_config` raises its own `ValidationError`, which slipped past callers' `except ValueError` guards; the adapter normalises it back to the documented contract.
- The email test suite works against `btx_lib_mail` 1.5.0, which streams messages through the low-level SMTP envelope (`MAIL FROM` / `RCPT TO` / `DATA`) instead of `sendmail` and exposes `ConfMail.smtp_password` as a `SecretStr`.

### Changed
- Dependency floor raised to `btx_lib_mail>=1.5.0`. The email tests assert against the streaming SMTP contract introduced there, and they do not pass on 1.4.0.
- Email tests drive an SMTP double that implements the real `smtplib` contract and records the delivered envelope, replacing a bare `MagicMock` that accepted any call and asserted nothing about delivery.
- Cleared `[tool.pip-audit].ignore-vulns`. The audit runs against the resolved dependency tree, which no longer contains any of the listed packages at an affected version, so every entry was inert; the table now documents when an entry is warranted.

## [1.9.3] 2026-06-14

### Changed
- Added a `typed_click.py` facade wrapping rich-click's `option` / `version_option` decorators behind explicit, fully-known signatures, keeping the CLI strict-clean under pyright 1.1.410 (`reportUnknownMemberType`) without disabling the rule (ignore isolated to the facade).
- Bumped internal dependency floors: `lib_cli_exit_tools>=2.3.2`, `lib_log_rich>=6.3.5`, `lib_layered_config>=5.5.2`, `btx_lib_mail>=1.3.2`.

## [1.9.2] - 2026-03-27

### Changed
- Config backups now include `/etc/systemd/system/*.wants/` symlink directories  -  enabled/disabled service state is preserved in the backup
- `exclude_patterns` default changed from `["/etc/systemd/system/*.wants"]` to `[]` with commented-out examples for optional exclusions

## [1.9.1] - 2026-03-27

### Changed
- Systemd service: added `setup-keys` as third `ExecStartPre` step  -  new servers get SSH keys deployed automatically on every backup run
- Systemd service: fixed config path in comments, clarified `--target app --force` deployment
- Updated INSTALL.md Quick Start to use `--target app --force` with correct system path

## [1.9.0] - 2026-03-27

### Changed
- **Breaking (config):** Replaced single `retention_count` with three independent settings:
  - `zfs_retention_count` (default: 3)  -  ZFS snapshots per server
  - `config_retention_count` (default: 30)  -  config backup archives per server
  - `packagelist_retention_count` (default: 30)  -  package list files per server
- Users with `retention_count` in custom config must migrate to the new keys
- Updated module_reference.md to v1.8.0 with complete backup system documentation

## [1.8.0] - 2026-03-27

### Added
- Package list backup: saves `dpkg --get-selections` and `dpkg -l` output alongside config backups
- New `packages_backup.py` adapter with `backup_packages()` function
- Runs automatically after each config backup (per-server, supports local and remote via SSH)
- Retention policy applied independently per package list type
- `build_packages_filename()` domain function for consistent naming
- 12 new tests covering remote, local, dry-run, and retention scenarios
- README: package restore instructions (`dpkg --set-selections`, `apt-get dselect-upgrade`)
- README, CONFIG.md, INSTALL.md: best-practice note about using `99-myconfig.toml` for overrides
- All default config TOML files: "DO NOT EDIT" header directing users to `99-myconfig.toml`

## [1.7.5] - 2026-03-27

### Changed
- Updated CVE exclusion list: added `CVE-2026-25645` (requests 2.32.5  -  env-only, not a project dependency)

### Fixed
- Suppressed `S603` (subprocess call) lint rule in tests via per-file-ignores  -  subprocess calls with list args are safe in test code, fixes ruff version mismatch between local (0.15.6) and CI (0.15.8)

## [1.7.4] - 2026-03-25

### Changed
- README: document PBS support alongside PVE (description, features, requirements, config example with PBS paths)

## [1.7.3] - 2026-03-25

### Added
- Proxmox Backup Server (PBS) paths in default `config_paths`: `/etc/proxmox-backup`, `/var/lib/proxmox-backup`
- Clarified PVE-only vs PBS-only comments in default backup config

## [1.7.2] - 2026-03-24

### Fixed
- Backup summary email never sent: `_send_summary_email` double-extracted the `[email]` config section, resulting in empty EmailConfig (no from_address, smtp_hosts, or recipients)

## [1.7.1] - 2026-03-24

### Removed
- Site-specific `/rotek` paths from default backup config (belong in user/host config, not defaults)

## [1.7.0] - 2026-03-24

### Added
- `authorized_keys_path` config option for `setup-keys` (default: `/etc/pve/priv/authorized_keys`)
- Direct SSH key deployment via `cat >>` instead of `ssh-copy-id` (fixes Proxmox pmxcfs FUSE issue)
- Idempotent key deployment: checks if key already present before appending
- 16 new tests for `ssh/commands.py` (coverage 25% → 100%)
- 12 new tests for `domain/behaviors.py` (coverage 75% → 100%)
- 9 new tests for `adapters/email/config.py` (coverage 84% → 100%)

### Fixed
- `setup-keys` now works reliably on Proxmox VE where `~/.ssh/authorized_keys` is a symlink to `/etc/pve/priv/authorized_keys` on a FUSE filesystem

### Changed
- README: documented `authorized_keys_path` config option and pmxcfs workaround

## [1.6.4] - 2026-03-24

### Changed
- Renamed systemd units from `proxmox-srvbackup-backup.{service,timer}` to `proxmox-srvbackup.{service,timer}`
- Service now auto-upgrades to latest PyPI version before each backup run (`ExecStartPre`)
- Fully documented service file with installation steps, prerequisites, and log commands
- README: updated systemd section with auto-upgrade behavior and log commands

## [1.6.3] - 2026-03-24

### Changed
- README: added ZFS snapshot restore instructions (`zfs recv` dry-run, force, staging)

## [1.6.2] - 2026-03-24

### Changed
- README: added "Hardening the backup server" section (SSH access restrictions for PBS)
- README: documented `setup-keys` idempotency (safe to re-run when adding new nodes)
- README: documented email notification content (subject tags, per-server report)

## [1.6.1] - 2026-03-24

### Changed
- README: added config backup restore instructions (preserves uid/gid and permissions)
- README: clarified ZFS snapshot scope (rpool only makes sense when VMs/CTs use a separate volume)
- README: documented that email notifications are disabled by default
- README: expanded notification description with subject tags and report content
- README: clarified systemd units require manual installation with link to setup section
- README: simplified install instructions to PyPI only
- CONFIG.md: documentation improvements

## [1.6.0] - 2026-03-23

### Added
- Pull-based backup system for Proxmox VE server fleets (`backup` command)
- Configuration file backup via SSH pipe (tar archives, no temp files on remote)
- ZFS rpool recursive snapshot backup via SSH (`zfs send -R | gzip`)
- Parallel backup execution across multiple servers (configurable thread pool)
- Per-server SSH key generation and deployment (`setup-keys` command)
- Automatic retention management (keeps N newest backups per server)
- Per-server backup type control (`backup_configfiles`, `backup_snapshot` booleans)
- Email notifications with backup status summaries after each run
- Systemd timer/service units for daily automated backups at 04:30
- `BackupSettings` typed dataclass replacing raw dict for backup config extraction
- Domain models: `ServerConfig`, `BackupResult`, `BackupSummary` frozen dataclasses
- `BackupType` enum (`config`, `zfs`, `all`) for CLI `--type` option
- `SSHConnectionError`, `SnapshotError`, `RetentionError` domain exceptions
- SSH command adapter (`ssh_run`, `ssh_pipe_to_file`, `local_run`, `local_pipe_to_file`)
- In-memory backup adapter for testing
- 51 new tests (30 per-server, 21 backup adapter unit tests)
- `@pytest.mark.proxmox` marker for tests requiring real Proxmox VE nodes
- Backup configuration section in `.env.example` with all settings documented
- Per-server `.env` overrides (`BACKUP__SERVERS__<NAME>__<KEY>=value`)
- `_as_bool()` helper for coercing TOML bools and .env strings consistently

### Changed
- `BackupAllServers` and `BackupSingleServer` protocols now include `backup_types` parameter
- README rewritten with full project description, CLI reference, and backup documentation
- CONFIG.md updated with backup configuration section and per-server settings
- DEVELOPMENT.md updated with current make targets and `bmk` delegation
- CONTRIBUTING.md updated with backup-relevant examples and SSH key guidance
- INSTALL.md updated with post-installation setup section
- CLAUDE.md project structure updated to reflect all backup/SSH/systemd files
- `pyproject.toml` description and keywords updated to reflect backup tool purpose

### Fixed
- `is_local` field now correctly coerced from .env string values (was truthy for `"false"`)
- Broken doctests in `behaviors.py` after `BackupResult` import removal

## [1.5.2] - 2026-03-05

### Fixed
- Re-release as 1.5.2: PyPI rejected 1.5.1 due to filename reuse after prior upload deletion

### Changed
- `get_permission_defaults()` now returns a `PermissionDefaults` Pydantic model instead of a raw dict, with typed field access and `dir_mode_for()`/`file_mode_for()` methods
- `EmailSpy` now stores captured calls as `CapturedEmail` and `CapturedNotification` frozen dataclasses instead of `list[dict[str, Any]]`

### Added
- Tests for `--env-file` CLI option (argument passing, validation, end-to-end integration)

## [1.5.1] - 2026-03-05 [YANKED]

### Changed
- `get_permission_defaults()` now returns a `PermissionDefaults` Pydantic model instead of a raw dict, with typed field access and `dir_mode_for()`/`file_mode_for()` methods
- `EmailSpy` now stores captured calls as `CapturedEmail` and `CapturedNotification` frozen dataclasses instead of `list[dict[str, Any]]`

### Added
- Tests for `--env-file` CLI option (argument passing, validation, end-to-end integration)

## [1.5.0] - 2026-03-02

### Added
- `--env-file PATH` global CLI option to load an explicit `.env` file instead of searching upward from the working directory
- `dotenv_path` parameter added to `GetConfig` protocol, config loader, and in-memory adapter
- `__all__` to `__init__conf__.py` listing all public symbols
- `@pytest.mark.integration` marker on email integration tests

### Fixed
- Subprocess tests (`test_module_entry_subprocess_help`, `test_module_entry_subprocess_version`) now pass without editable install by setting `PYTHONPATH` to `src/`
- pip-audit CVE-2025-8869 ignore (pip is environment-level, not a project dependency)

### Changed
- CI workflow: dynamic Python version matrix extracted from `pyproject.toml` classifiers
- CI workflow: ruff cache restricted to GitHub-hosted runners
- CI workflow: bandit reads configuration from `pyproject.toml` (`-c pyproject.toml`)
- CI workflow: Codecov upload uses dynamically resolved latest Python version
- Release workflow: `actions/upload-artifact` upgraded to v7
- Added `[tool.hatch.metadata]` and `[tool.bashate]` sections to `pyproject.toml`
- Documentation updates: CONFIG.md, README.md, DEVELOPMENT.md for `--env-file` option

## [1.4.1] - 2026-02-13

### Fixed
- `reset_git_history.sh`: fixed shellcheck SC1083 warning by quoting `HEAD^{tree}` and normalized indentation to 4 spaces (shfmt)

### Changed
- Updated Makefile from v2.2.1 to v2.3.3
- Bumped dependency minimums: `lib_cli_exit_tools` >=2.3.0, `lib_log_rich` >=6.3.3, `lib_layered_config` >=5.4.1
- Added CVE ignore entries for CVE-2026-26007 and CVE-2026-25990
- Updated CI/CD workflows and added Bash 4+ requirement for macOS

## [1.4.0] - 2026-02-13

### Changed
- **Build automation**: replaced `scripts/` directory with `bmk`-based Makefile (`uvx bmk@latest`); all build, test, bump, push, and release tasks now delegated to `bmk`
- Makefile updated to v2.2.1 with alias targets, trailing argument forwarding, and new commands (config, email, info, logdemo)

## [1.3.1] - 2026-02-13

### Fixed
- `tests/test_metadata_sync.py`: replaced `importlib.metadata` lookups with direct `pyproject.toml` reads  -  tests no longer fail when the package is not installed in the test environment (uvx)
- Makefile `dev` target now correctly installs dev extras (`uv pip install -e ".[dev]"`)

### Changed
- CLAUDE.md: updated project structure trees to reflect actual codebase (added `entry.py`, `domain/errors.py`, `adapters/memory/`, `adapters/config/permissions.py`, `adapters/email/validation.py`; removed deleted `traceback.py`)
- CLAUDE.md: rewrote Make targets table to match new `bmk`-based Makefile (added aliases, new targets; removed obsolete `menu`, `test-slow`)
- CLAUDE.md: corrected versioning documentation  -  runtime metadata is served from `__init__conf__.py` constants, not `importlib.metadata`
- CLAUDE.md: replaced stale `scripts/` instrumentation section with `bmk` delegation note
- CLAUDE.md: updated `make test-slow` references to `make testintegration`

## [1.3.0] - 2026-02-01

### Added
- **File permission options for `config-deploy`**: `--permissions/--no-permissions`, `--dir-mode`, `--file-mode`
- **Configurable permission defaults** in `[lib_layered_config.default_permissions]` (app/host: 755/644, user: 700/600)
- **Octal string support** in config files (`"0o755"`, `"755"`, or decimal `493`)

### Changed
- `deploy_configuration()` accepts `set_permissions`, `dir_mode`, `file_mode` parameters
- CONFIG.md: comprehensive CLI options reference, `sudo -u` deployment examples

## [1.2.1] - 2026-02-01

### Changed
- **Profile validation** now delegates to `lib_layered_config.validate_profile_name()` with comprehensive security checks:
  - Maximum length enforcement (64 characters)
  - Empty string rejection
  - Windows reserved name rejection (CON, PRN, AUX, NUL, COM1-9, LPT1-9)
  - Leading character validation (must start with alphanumeric)
  - Path traversal prevention (/, \, ..)
- `validate_profile()` now accepts optional `max_length` parameter for customization

### Added
- `40-layered-config.toml` in `defaultconfig.d/` documenting lib_layered_config integration settings
- Profile validation tests for length limits, empty strings, Windows reserved names, and leading character rules
- Profile name requirements documentation in CONFIG.md and README.md

### Removed
- Custom `_PROFILE_PATTERN` regex  -  replaced by lib_layered_config's built-in validation

## [1.2.0] - 2026-01-30

### Added
- **Attachment security settings** for email configuration (`[email.attachments]` section in `50-mail.toml`)
  - `allowed_extensions` / `blocked_extensions`  -  whitelist/blacklist file extensions
  - `allowed_directories` / `blocked_directories`  -  whitelist/blacklist attachment source directories
  - `max_size_bytes`  -  maximum attachment file size (default 25 MiB, 0 to disable)
  - `allow_symlinks`  -  whether symbolic links are permitted (default false)
  - `raise_on_security_violation`  -  raise or skip on violations (default true)
- New `EmailConfig` fields for attachment security with Pydantic validators
- `load_email_config_from_dict()` now flattens nested `[email.attachments]` section

### Changed
- Bumped `btx_lib_mail` dependency from `>=1.2.1` to `>=1.3.0` for attachment security features

## [1.1.2] - 2026-01-28

### Fixed
- Coverage SQLite "database is locked" errors on Python 3.14 free-threaded builds and network mounts (SMB/NFS)
- Removed bogus `COVERAGE_NO_SQL=1` environment variable from `scripts/test.py` (not a real coverage.py setting)
- CI workflow now sets `COVERAGE_FILE` to `runner.temp` so coverage always writes to local disk
- **Import-linter was a silent no-op** in `make test` / `make push`  -  `python -m importlinter.cli lint` silently exits 0 without checking; replaced with `lint-imports` (the working console entry point)
- CI/local parameter mismatches: ruff now targets `.` (not hardcoded `src tests notebooks`), pytest uses `python -m pytest` with `--cov=src/$PACKAGE_MODULE`, `--cov-fail-under=90`, and `-vv` matching local runs
- `scripts/test.py` bandit source path now reads `src-path` from `[tool.scripts.test]` instead of hardcoding `Path("src")`
- `scripts/test.py` module-level `_default_env` now rebuilt with configured `src_path` before running checks
- `run_slow_tests()` now reads pytest verbosity from `[tool.scripts.test].pytest-verbosity` instead of hardcoding `"-vv"`

### Changed
- **pyproject.toml as single source of truth**: CI workflow extracts all tool configuration (src-path, pytest-verbosity, coverage-report-file, fail_under, bandit skips) from `pyproject.toml` via metadata step  -  workflow is portable across projects without editing
- `scripts/test.py` removed module-level `PACKAGE_SRC` constant; bandit source path computed from `config.src_path` inside the functions that need it
- `make push` now accepts an unquoted message as trailing words (e.g. `make push fix typo in readme`); commit message format is `<version> - <message>`, defaulting to `<version> - chores` when no message is given
- Removed interactive commit-message prompt from `push.py`  -  message is either provided via CLI args / `COMMIT_MESSAGE` env var, or defaults to `"chores"`

### Added
- `pytest_configure` hook in `tests/conftest.py` that redirects coverage data to `tempfile.gettempdir()` and purges stale SQLite journal files before each run

## [1.1.1] - 2026-01-28

### Fixed
- CLAUDE.md: replaced stale package name `bitranox_template_cli_app_config_log_mail` with `proxmox_srvbackup` throughout
- Brittle SMTP mock assertions in `test_cli.py` now use structured `call_args` attributes instead of `str()` coercion
- Stale docstring in `__init__conf__.py` claiming "adapters/platform layer"  -  corrected to "Package-level metadata module"
- Weak OR assertion in `test_cli.py` for SMTP host display  -  replaced with two independent assertions
- Removed stale `# type: ignore[reportUnknownVariableType]` from `sender.py` (`btx_lib_mail.ConfMail` now has proper type annotations)
- Late function-body imports in `adapters/cli/commands/config.py` moved to module-level for consistency

### Removed
- Dead code: unused `_format_value()` and `_format_source()` wrappers in `adapters/config/display.py`

### Added
- `__all__` to `__init__conf__.py` listing all public symbols
- `tests/test_enums.py` with parametrized tests for `OutputFormat` and `DeployTarget`
- Expanded `tests/test_behaviors.py` with return type, constant value, and constant-usage checks
- Python 3.14 classifier in `pyproject.toml`
- Codecov upload step in CI workflow (gated to `ubuntu-latest` + `3.13`)
- Edge-case tests for `parse_override`: bare `=value`, bare `=`, and CLI `--set ""` empty string
- Duplication-tracking comments for CI metadata extraction scripts

### Changed
- `tests/test_display.py` rewritten to test `_format_raw_value` and `_format_source_line` directly (replacing dead wrapper tests)

## [1.1.0] - 2026-01-27

### Changed
- Replaced `MockConfig` in-memory adapter with real `Config` objects in all tests (`config_factory` / `inject_config` fixtures)
- Replaced `MagicMock` Config objects in CLI email tests with real `Config` instances
- Unified test names to BDD-style `test_when_<condition>_<behavior>` pattern in `test_cli.py`
- Email integration tests now load configuration via `lib_layered_config` instead of dedicated `TEST_SMTP_SERVER` / `TEST_EMAIL_ADDRESS` environment variables

### Added
- Cache effectiveness tests for `get_config()` and `get_default_config_path()` LRU caches (`tests/test_cache_effectiveness.py`)
- Callable Protocol definitions in `application/ports.py` for all adapter functions, with static conformance assertions and `tests/test_ports.py`
- `ExitCode` IntEnum (`adapters/cli/exit_codes.py`) with POSIX-conventional exit codes for all CLI error paths
- `logdemo` and `config-generate-examples` CLI commands
- `--set SECTION.KEY=VALUE` repeatable CLI option for runtime configuration overrides (`adapters.config.overrides` module)
- Unit tests for config overrides and display module (sensitive key matching, redaction, nested rendering)

### Removed
- Dead code: `raise_intentional_failure()`, `noop_main()`, `cli_main()`, duplicate `cli_session` orchestration, catch-log-reraise in `send_email()`
- Replaced dead `ConfigPort`/`EmailPort` protocol classes with callable Protocol definitions

### Fixed
- POSIX-conventional exit codes across all CLI error paths (replacing hardcoded `SystemExit(1)`)
- Sensitive value redaction: word-boundary matching to avoid false positives, nested dict/list redaction, TOML sub-section rendering
- Email validation: reject bogus addresses (`@`, `user@`, `@domain`); IPv6 SMTP host support; credential construction
- Profile name validation against path traversal
- Security: list-based subprocess calls in scripts, sensitive env-var redaction in test output, stale CVE exclusion cleanup
- Documentation: wrong project name references, truncated CLI command names, stale import paths, wrong layer descriptions
- CI: `actions/download-artifact` version mismatch, stale `codecov.yml` ignore patterns
- Unified `__main__.py` and `adapters/cli/main.py` error handling via delegation

### Changed
- Precompile all regex patterns in `scripts/` as module-level constants for consistent compilation
- **LIBRARIES**: Replace custom redaction/validation with `lib_layered_config` redaction API and `btx_lib_mail` validators; bump both libraries
- **LIBRARIES**: Replace stdlib `json` with `orjson`; replace `urllib` with `httpx` in scripts
- **ARCHITECTURE**: Purified domain layer  -  `emit_greeting()` renamed to `build_greeting()` (returns `str`, no I/O); decoupled `display.py` from Click
- **DATA ARCHITECTURE**: Consolidated `EmailConfig` into single Pydantic `BaseModel` (eliminated dataclass conversion chain)

## [1.0.0] - 2026-01-15

### Added
- Slow integration test infrastructure (`make test-slow`, `@pytest.mark.slow` marker)
- `pydantic>=2.0.0` dependency for boundary validation
- `CLIContext` dataclass replacing untyped `ctx.obj` dict
- Pydantic models: `EmailSectionModel`, `LoggingConfigModel`
- `application/ports.py` with Protocol definitions; `composition/__init__.py` wiring layer

### Changed
- **BREAKING**: Full Clean Architecture refactoring into explicit layer directories (`domain/`, `application/`, `adapters/`, `composition/`)
- CLI restructured from monolithic `cli.py` into focused `cli/` package with single-responsibility modules
- Type hints modernized to Python 3.10+ style
- Removed backward compatibility re-exports; tests import from canonical module paths
- `import-linter` contracts enforce layer dependency direction
- `make test` excludes slow tests by default

## [0.2.5] - 2026-01-01

### Changed
- Bumped `lib_log_rich` to >=6.1.0 and `lib_layered_config` to >=5.2.0

## [0.2.4] - 2025-12-27

### Fixed
- Intermittent test failures on Windows when parsing JSON config output (switched to `result.stdout`)

## [0.2.3] - 2025-12-15

### Changed
- Lowered minimum Python version from 3.13 to 3.10; expanded CI matrix accordingly

## [0.2.2] - 2025-12-15

### Added
- Global `--profile` option for profile-specific configuration across all commands

### Changed
- **BREAKING**: Configuration loaded once in root CLI command and stored in Click context for subcommands
- Subcommand `--profile` options act as overrides that reload config when specified

## [0.2.0] - 2025-12-07

### Added
- `--profile` option for `config` and `config-deploy` commands
- `OutputFormat` and `DeployTarget` enums for type-safe CLI options
- LRU caching for `get_config()` (maxsize=4) and `get_default_config_path()`

### Fixed
- UTF-8 encoding issues in subprocess calls across different locales

## [0.1.0] - 2025-12-07

### Added
- Email sending via `btx-lib-mail` integration: `send-email` and `send-notification` CLI commands
- Email configuration support with `EmailConfig` dataclass and validation
- Real SMTP integration tests using `.env` configuration

## [0.0.1] - 2025-11-11
- Bootstrap
