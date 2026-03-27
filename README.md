# proxmox_srvbackup

<!-- Badges -->
[![CI](https://github.com/bitranox/proxmox_srvbackup/actions/workflows/default_cicd_public.yml/badge.svg)](https://github.com/bitranox/proxmox_srvbackup/actions/workflows/default_cicd_public.yml)
[![CodeQL](https://github.com/bitranox/proxmox_srvbackup/actions/workflows/codeql.yml/badge.svg)](https://github.com/bitranox/proxmox_srvbackup/actions/workflows/codeql.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Open in Codespaces](https://img.shields.io/badge/Codespaces-Open-blue?logo=github&logoColor=white&style=flat-square)](https://codespaces.new/bitranox/proxmox_srvbackup?quickstart=1)
[![PyPI](https://img.shields.io/pypi/v/proxmox-srvbackup.svg)](https://pypi.org/project/proxmox_srvbackup/)
[![PyPI - Downloads](https://img.shields.io/pypi/dm/proxmox_srvbackup.svg)](https://pypi.org/project/proxmox_srvbackup/)
[![Code Style: Ruff](https://img.shields.io/badge/Code%20Style-Ruff-46A3FF?logo=ruff&labelColor=000)](https://docs.astral.sh/ruff/)
[![codecov](https://codecov.io/gh/bitranox/proxmox_srvbackup/graph/badge.svg?token=UFBaUDIgRk)](https://codecov.io/gh/bitranox/proxmox_srvbackup)
[![Maintainability](https://qlty.sh/badges/041ba2c1-37d6-40bb-85a0-ec5a8a0aca0c/maintainability.svg)](https://qlty.sh/gh/bitranox/projects/proxmox_srvbackup)
[![Known Vulnerabilities](https://snyk.io/test/github/bitranox/proxmox_srvbackup/badge.svg)](https://snyk.io/test/github/bitranox/proxmox_srvbackup)
[![security: bandit](https://img.shields.io/badge/security-bandit-yellow.svg)](https://github.com/PyCQA/bandit)


### What it does

`proxmox_srvbackup` backs up an entire fleet of Proxmox VE and Proxmox Backup
Server nodes from a single backup server. It uses a **pull-based** approach:
the backup server connects to each node over SSH, streams a tar archive of
configuration files and a recursive ZFS rpool snapshot, and writes them
directly to local storage. No agent or additional software runs on the
Proxmox nodes themselves.

### Why pull-based?

Push-based backups rely on each node to initiate its own backup. If a node
is compromised, misconfigured, or offline at the scheduled time, the backup
silently fails. A pull model keeps the backup server in control: it decides
when, what, and how to back up, and it knows immediately when a node is
unreachable. Per-server SSH keys with minimal privileges limit the blast
radius if any single key is exposed.

### Hardening the backup server

The backup server (PBS) holds SSH keys that grant root access to every
Proxmox node. Restrict inbound SSH access so that only trusted hosts
(management workstations, jump hosts) can reach it:

- **Proxmox firewall**: allow SSH (port 22) only from specific IPs or
  VLANs in the datacenter/cluster firewall rules.
- **`sshd_config`**: use `AllowUsers root@<management-ip>` or
  `Match Address` blocks to reject connections from untrusted sources.
- **Fail2ban / SSHGuard**: rate-limit brute-force attempts on the
  remaining allowed sources.

If an attacker gains SSH access to the PBS, they can reach every node.
Limiting who can SSH into the PBS is the single most effective hardening
measure for this setup.

### How it works

1. **SSH key setup** -- `setup-keys` generates an ed25519 keypair per server
   and deploys the public key using an existing bootstrap key.
2. **Config backup** -- SSH to each node, `tar` the configured paths
   (`/etc/pve`, `/etc/proxmox-backup`, `/etc/network`, cron jobs, corosync,
   etc.), and pipe the compressed archive directly to a local file. No temp
   files on the remote. Non-existent paths are silently skipped.
3. **Package list backup** -- After each config backup, capture the installed
   package list via `dpkg --get-selections` (machine-readable, re-importable)
   and `dpkg -l` (human-readable with versions). These text files are stored
   alongside config archives and subject to the same retention policy.
4. **ZFS snapshot** -- Create a recursive ZFS snapshot of the configured
   pool (typically rpool) on the node, stream it with `zfs send -R | gzip -1`
   to a local `.zfs.gz` file, then destroy the remote snapshot. This only
   makes sense when VMs and containers do **not** sit on rpool but on a
   separate storage volume -- otherwise the snapshot would include all guest
   data and be impractically large.
5. **Parallel execution** -- Backups can run across all servers concurrently
   (configurable thread pool, default 4 threads).
6. **Retention** -- After each run, old backups exceeding `retention_count`
   are automatically pruned.
7. **Notification** -- After each backup run, a summary email is sent
   (if configured). The subject line indicates overall status (`[OK]`,
   `[WARNING]`, or `[ERROR]`). The body lists every server with its
   status, duration, and any error messages for failed config or ZFS
   backups. Email is disabled by default -- see
   [Email Configuration](#email-configuration).
8. **Scheduling** -- Systemd timer/service units are shipped under
   `src/proxmox_srvbackup/adapters/config/systemd/` and must be copied
   manually to `/etc/systemd/system/` (see
   [Automated Backups with systemd](#automated-backups-with-systemd)).
   Default schedule: daily at 04:30 with random jitter.

### Features

- Pull-based backup of Proxmox VE and PBS configuration files (tar archives via SSH pipe)
- Installed package list backup (`dpkg --get-selections` and `dpkg -l`) alongside config backups
- Pull-based ZFS rpool recursive snapshots (`zfs send -R | gzip`)
- Parallel backup execution across multiple servers (configurable thread pool)
- Per-server SSH key generation and deployment (`setup-keys` command)
- Automatic retention management (keeps N newest backups per server)
- Email notifications with status summaries after each backup run
- Systemd timer/service units for daily automated backups
- Layered configuration system with defaults, app, host, user, .env, env vars, and CLI overrides
- Rich CLI output with [rich-click](https://github.com/ewels/rich-click) styling
- Structured logging with [lib_log_rich](https://github.com/bitranox/lib_log_rich) (console, journald, Graylog/GELF)

### Requirements

- **Python 3.10+**
- **Proxmox VE / PBS** nodes accessible via SSH from the backup server
- **ZFS** on the backup server for storing snapshot streams
- **SSH** access with per-server keys (generated via `setup-keys` command)
- Runtime dependencies: `rich-click`, `lib_layered_config`, `lib_log_rich`, `lib_cli_exit_tools`, `btx_lib_mail`, `pydantic`, `orjson`

---

## Install

[uv](https://docs.astral.sh/uv/) is the recommended package manager (10-20x faster than pip/poetry).

### Install uv (if not already installed)

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Copy the actual binaries
cp /root/.local/bin/uv /usr/local/bin/uv
cp /root/.local/bin/uvx /usr/local/bin/uvx

# Ensure world-executable
chmod 755 /usr/local/bin/uv /usr/local/bin/uvx
```

### One-shot run (no install needed)

```bash
uvx proxmox_srvbackup@latest --help
```

### Persistent install as CLI tool

```bash
# Install latest python
install_latest_python_gcc.sh
# Pin uv to the latest python
uv python pin /opt/python-latest/bin/python3
# Install from PyPI
uv tool install --python /opt/python-latest/bin/python3 proxmox_srvbackup
# Update (requires network)
uv tool upgrade proxmox_srvbackup
# deploy (overwrite) new default config
proxmox-srvbackup config-deploy --target app --force
# Run
proxmox-srvbackup --help
```

For alternative install paths (pip, pipx, source builds, etc.), see
[INSTALL.md](INSTALL.md). All supported methods register both the
`proxmox_srvbackup` and `proxmox-srvbackup` commands on your PATH.

---

## Quick Start

```bash
# 1. Verify
proxmox-srvbackup --version

# 2. Deploy default configuration
proxmox-srvbackup config-deploy --target app --force
# it is best practice to create a 99-myconfig.toml to override default settings, instead of editing default config
# otherwise updates might overwrite Your config !

# 3. Edit the configuration to add your servers, either via config or .env file
#    (see Configuration section below)

# 4. Generate and deploy SSH keys to all servers
proxmox-srvbackup setup-keys

# 5. Run a dry-run backup to verify connectivity
proxmox-srvbackup backup --dry-run

# 6. Run the actual backup
proxmox-srvbackup backup
```

---

## Configuration

See [CONFIG.md](CONFIG.md) for the full configuration reference, including precedence rules, profile support, and customization best practices.

> **Best practice:** Do not edit the deployed default config files directly. Instead,
> create a `99-myconfig.toml` in the same directory to override only the settings you
> need. The layered config system merges numbered `.toml` files in order, so your
> `99-myconfig.toml` takes precedence over the defaults. This way, package updates
> can safely replace the default files without overwriting your customizations.

### Backup Configuration

The `[backup]` section in configuration controls backup behavior:

```toml
[backup]
backup_base_dir = "/mnt/zpool-ssd/px-node-backups"
max_parallel = 4                # concurrent backup threads
zfs_retention_count = 3         # number of ZFS snapshots to keep per server
config_retention_count = 30     # number of config backups to keep per server
packagelist_retention_count = 30 # number of package list files to keep per server
ssh_user = "root"
ssh_connect_timeout = 15        # seconds
ssh_key_dir = "/root/.ssh"
ssh_key_prefix = "backup_pull"
bootstrap_key = "/path/to/shared/bootstrap.key"
authorized_keys_path = "/etc/pve/priv/authorized_keys"  # Proxmox default

[backup.config_paths]
paths = [
    # Proxmox VE cluster & node config (PVE only)
    "/etc/pve",                    # cluster config, VM/CT configs, storage, users, SSL, HA, SDN
    "/etc/network",                # interfaces, bridges, VLANs, bonds
    "/etc/vzdump.conf",            # default backup settings
    # System identity & DNS
    "/etc/hostname",
    "/etc/hosts",
    "/etc/resolv.conf",
    # Package repos
    "/etc/apt/sources.list",
    "/etc/apt/sources.list.d",
    # Scheduled tasks
    "/etc/cron.d",
    "/etc/cron.daily",
    "/etc/cron.hourly",
    "/etc/cron.weekly",
    # Service daemon settings (PVE only)
    "/etc/default/pvedaemon",
    "/etc/default/pveproxy",
    # Kernel & boot
    "/etc/modprobe.d",
    "/etc/kernel/cmdline",
    "/etc/default/grub",
    "/etc/sysctl.d",
    # Systemd customizations
    "/etc/systemd/system",
    # Time sync
    "/etc/chrony",
    "/etc/systemd/timesyncd.conf",
    # Mail relay
    "/etc/postfix",
    "/etc/aliases",
    # SSH
    "/etc/ssh/sshd_config",
    # Storage subsystems
    "/etc/lvm",
    # Templates & ISOs (PVE only)
    "/var/lib/vz/template/iso",
    "/var/lib/vz/template/cache",
    # Cluster state (PVE only)
    "/var/lib/corosync",
    "/var/lib/pve-cluster",
    # Proxmox Backup Server (PBS only)
    "/etc/proxmox-backup",         # datastore.cfg, user.cfg, acl.cfg, remote.cfg, sync.cfg, etc.
    "/var/lib/proxmox-backup",     # task logs, tokens, catalog cache
]
exclude_patterns = [
    # "/etc/systemd/system/*.wants",  # exclude if you do not want to backup the enabled/disabled states of services
    # "/var/lib/vz/template/cache",   # can be downloaded, might be no need to save it
]

# Server definitions
[backup.servers.proxmox01]
hostname = "proxmox01.example.com"
zfs_pool = "rpool"

[backup.servers.proxmox02]
hostname = "proxmox02.example.com"
zfs_pool = "rpool"

# A server without ZFS rpool (config-only backup)
[backup.servers.proxmox-fw]
hostname = "proxmox-fw.example.com"
backup_configfiles = true
backup_snapshot = false

# The backup server itself (commands run locally, no SSH)
[backup.servers.proxmox-pbs]
hostname = "proxmox-pbs.example.com"
zfs_pool = "rpool"
is_local = true
```

### Backup Storage Layout

Backups are organized under `backup_base_dir`:

```
/mnt/zpool-ssd/px-node-backups/
├── proxmox01/
│   ├── configs/
│   │   ├── backup_config_proxmox01_2026-03-23_04-30-00.tar.gz
│   │   ├── packages_selections_proxmox01_2026-03-23_04-30-00.txt
│   │   ├── packages_list_proxmox01_2026-03-23_04-30-00.txt
│   │   ├── backup_config_proxmox01_2026-03-22_04-30-00.tar.gz
│   │   ├── packages_selections_proxmox01_2026-03-22_04-30-00.txt
│   │   ├── packages_list_proxmox01_2026-03-22_04-30-00.txt
│   │   └── ...
│   └── snapshots/
│       ├── rpool_snapshot_proxmox01_2026-03-23_04-30-00.zfs.gz
│       └── ...
├── proxmox02/
│   ├── configs/
│   └── snapshots/
└── proxmox-pbs/
    ├── configs/
    └── snapshots/
```

### Restoring Config Backups

Config archives are standard `tar.gz` files that preserve full POSIX metadata
(uid, gid, permissions). To restore with correct ownership and permissions,
extract as root with `--same-owner` (default for root) and `-p` to preserve
permissions:

```bash
# Restore to the original paths on the target server
sudo tar -xzpf backup_config_proxmox01_2026-03-23_04-30-00.tar.gz -C /

# Preview contents before restoring
tar -tzf backup_config_proxmox01_2026-03-23_04-30-00.tar.gz

# Restore to a staging directory for inspection
sudo tar -xzpf backup_config_proxmox01_2026-03-23_04-30-00.tar.gz -C /tmp/restore-staging/

# Verify preserved permissions and ownership
tar -tvf backup_config_proxmox01_2026-03-23_04-30-00.tar.gz
```

**Important:** Always extract as root (`sudo`). Non-root extraction silently
maps all files to your user, losing the original uid/gid. The `-p` flag
preserves file permissions exactly as stored in the archive.

### Restoring Installed Packages

Each config backup includes two package list files:

- `packages_selections_<server>_<timestamp>.txt` -- output of `dpkg --get-selections` (machine-readable, suitable for bulk reinstall)
- `packages_list_<server>_<timestamp>.txt` -- output of `dpkg -l` (human-readable with version numbers, useful for auditing)

**Reinstall all packages from a selections file:**

```bash
# On the target server, set the package selections and install
sudo dpkg --set-selections < packages_selections_proxmox01_2026-03-23_04-30-00.txt
sudo apt-get dselect-upgrade
```

**Compare installed packages between two backups:**

```bash
diff packages_selections_proxmox01_2026-03-22_04-30-00.txt \
     packages_selections_proxmox01_2026-03-23_04-30-00.txt
```

**Check which version of a package was installed:**

```bash
grep nginx packages_list_proxmox01_2026-03-23_04-30-00.txt
```

### Restoring ZFS Snapshots

ZFS snapshot backups are gzip-compressed `zfs send -R` streams. Restore them
with `zfs receive` on the target server.

```bash
# List the contents of a snapshot stream (dry-run, no changes)
gunzip -c rpool_snapshot_proxmox01_2026-03-23_04-30-00.zfs.gz | zfs recv -n rpool

# Restore rpool from the backup (overwrites existing rpool datasets!)
gunzip -c rpool_snapshot_proxmox01_2026-03-23_04-30-00.zfs.gz | zfs recv -F rpool

# Restore to a different pool or dataset for inspection
gunzip -c rpool_snapshot_proxmox01_2026-03-23_04-30-00.zfs.gz | zfs recv -F tank/restore-staging
```

**Flags explained:**

| Flag | Description |
|------|-------------|
| `-n` | Dry-run: validates the stream without writing data |
| `-F` | Force: rolls back the target to its most recent snapshot before receiving |

**Important considerations:**

- `zfs recv -F rpool` **overwrites** the target pool's datasets. Make sure
  you are restoring to the correct server and pool.
- The `-R` flag used during backup means the stream is recursive -- all
  child datasets (e.g. `rpool/ROOT`, `rpool/data`) are included and will
  be restored.
- If the target pool already has snapshots or datasets that conflict,
  `zfs recv` will fail. Use `-F` to force rollback, or restore to a
  staging dataset first.
- Boot from a rescue system or live USB when restoring the root pool of
  a running system.

---

## CLI Reference

The CLI uses [rich-click](https://github.com/ewels/rich-click) for styled help output.

### Global Options

These options apply to all commands and must appear **before** the command name:

```bash
proxmox-srvbackup [OPTIONS] COMMAND [ARGS...]
```

| Option                         | Description                                               |
|--------------------------------|-----------------------------------------------------------|
| `--version`                    | Show version and exit                                     |
| `--traceback / --no-traceback` | Show full Python traceback on errors                      |
| `--profile NAME`               | Load configuration from a named profile                   |
| `--set SECTION.KEY=VALUE`      | Override a configuration setting (repeatable)             |
| `--env-file PATH`              | Explicit `.env` file path (skips upward directory search) |
| `--help`                       | Show help and exit                                        |

### Backup Commands

#### `backup` -- Pull backups from Proxmox servers

Connects to each configured server via SSH and pulls configuration archives and ZFS rpool snapshots to local backup storage.

```bash
proxmox-srvbackup backup [OPTIONS]
```

| Option          | Default     | Description                                         |
|-----------------|-------------|-----------------------------------------------------|
| `--server NAME` | all servers | Backup only this server (by name from config)       |
| `--type TYPE`   | `all`       | Backup type: `all`, `config`, or `zfs`              |
| `--dry-run`     | off         | Show what would be executed without running backups |

**Examples:**

```bash
# Backup all servers (config + ZFS)
proxmox-srvbackup backup

# Dry-run to verify connectivity and configuration
proxmox-srvbackup backup --dry-run

# Backup only configuration files (skip ZFS snapshots)
proxmox-srvbackup backup --type config

# Backup only ZFS snapshots
proxmox-srvbackup backup --type zfs

# Backup a single server
proxmox-srvbackup backup --server proxmox01

# Combine options
proxmox-srvbackup backup --server proxmox01 --type config --dry-run
```

**What happens during a backup:**

1. For each server (in parallel, up to `max_parallel` threads):
   - **Config backup**: SSH to the server, `tar` the configured paths, stream directly to a local `.tar.gz` file
   - **Package list**: Capture `dpkg --get-selections` and `dpkg -l` output, save as text files alongside config archives
   - **ZFS backup**: Create a recursive ZFS snapshot, `zfs send -R | gzip -1` piped to a local `.zfs.gz` file, then destroy the remote snapshot
2. Apply retention policy (delete oldest files exceeding `retention_count`)
3. Print a summary report
4. Send an email notification with the backup status (if email is configured)

#### `setup-keys` -- Generate and deploy SSH keys

Generates per-server ed25519 keypairs and deploys public keys to each remote server using the bootstrap key for initial access.

```bash
proxmox-srvbackup setup-keys
```

**What happens:**

1. For each non-local server in the configuration:
   - Generates an ed25519 keypair at `{ssh_key_dir}/{ssh_key_prefix}_{server_name}` (skips if it already exists)
   - Deploys the public key directly to the remote `authorized_keys_path`
     via SSH (defaults to `/etc/pve/priv/authorized_keys` for Proxmox VE)
   - Tests connectivity using the newly deployed key

**Why not `ssh-copy-id`?** Proxmox VE symlinks `~/.ssh/authorized_keys` to
`/etc/pve/priv/authorized_keys` on a FUSE filesystem (pmxcfs). `ssh-copy-id`
follows the symlink but the write silently fails. This tool deploys keys
directly to the actual file path.

**Idempotent -- safe to re-run:**

Running `setup-keys` again is harmless. Existing keypairs are skipped
(not overwritten), and the deployment checks whether the key is already
present before appending. When you add a new server to the configuration,
just run `setup-keys` again -- it will generate and deploy the key for the
new server while leaving all existing keys untouched:

```bash
# Added [backup.servers.proxmox-new] to the config? Just re-run:
proxmox-srvbackup setup-keys
```

**Prerequisites:**

- The `bootstrap_key` must be configured and provide SSH access to all servers
- The backup server must have `ssh-keygen` available

### Configuration Commands

#### `config` -- View merged configuration

```bash
proxmox-srvbackup config [OPTIONS]
```

| Option            | Default | Description                      |
|-------------------|---------|----------------------------------|
| `--format FORMAT` | `human` | Output format: `human` or `json` |
| `--section NAME`  | all     | Show only a specific section     |

**Examples:**

```bash
proxmox-srvbackup config
proxmox-srvbackup config --format json
proxmox-srvbackup config --section backup
proxmox-srvbackup config --section email
proxmox-srvbackup --profile production config
```

#### `config-deploy` -- Deploy configuration files

```bash
proxmox-srvbackup config-deploy [OPTIONS]
```

| Option                             | Required | Description                                         |
|------------------------------------|:--------:|-----------------------------------------------------|
| `--target TARGET`                  | Yes      | Target layer: `app`, `host`, or `user` (repeatable) |
| `--force`                          | No       | Overwrite existing configuration files              |
| `--profile NAME`                   | No       | Deploy to a profile-specific subdirectory           |
| `--permissions / --no-permissions` | No       | Enable/disable Unix permission setting              |
| `--dir-mode MODE`                  | No       | Override directory permissions (octal)              |
| `--file-mode MODE`                 | No       | Override file permissions (octal)                   |

**Examples:**

```bash
# Deploy user configuration
proxmox-srvbackup config-deploy --target user

# Deploy system-wide (requires root)
sudo proxmox-srvbackup config-deploy --target app

# Deploy host-specific configuration
sudo proxmox-srvbackup config-deploy --target host

# Overwrite existing files
proxmox-srvbackup config-deploy --target user --force

# Deploy with a profile
proxmox-srvbackup config-deploy --target user --profile production
```

> **Tip:** After deploying, create a `99-myconfig.toml` in the deployed directory
> to override settings instead of editing the default files. Updates may overwrite
> the deployed defaults, but your `99-myconfig.toml` will be preserved.

#### `config-generate-examples` -- Generate example config files

```bash
proxmox-srvbackup config-generate-examples --destination DIR [--force]
```

### Email Commands

#### `send-email` -- Send an email

```bash
proxmox-srvbackup send-email [OPTIONS]
```

| Option              | Required | Description                    |
|---------------------|:--------:|--------------------------------|
| `--to ADDRESS`      | Yes      | Recipient address (repeatable) |
| `--subject TEXT`    | Yes      | Email subject                  |
| `--body TEXT`       | Yes      | Plain-text body                |
| `--body-html TEXT`  | No       | HTML body                      |
| `--attachment PATH` | No       | File attachment (repeatable)   |

**Examples:**

```bash
proxmox-srvbackup send-email \
    --to admin@example.com \
    --subject "Test Email" \
    --body "Hello from proxmox_srvbackup!"

proxmox-srvbackup send-email \
    --to admin@example.com \
    --subject "Monthly Report" \
    --body "See attached." \
    --body-html "<h1>Report</h1>" \
    --attachment report.pdf
```

#### `send-notification` -- Send a plain-text notification

```bash
proxmox-srvbackup send-notification [OPTIONS]
```

| Option           | Required | Description                    |
|------------------|:--------:|--------------------------------|
| `--to ADDRESS`   | Yes      | Recipient address (repeatable) |
| `--subject TEXT` | Yes      | Email subject                  |
| `--message TEXT` | Yes      | Plain-text message body        |

**Examples:**

```bash
proxmox-srvbackup send-notification \
    --to ops@example.com \
    --subject "Backup Complete" \
    --message "All backups finished successfully"
```

### Informational Commands

```bash
# Display package metadata
proxmox-srvbackup info

# Greeting demo
proxmox-srvbackup hello

# Error-handling demo
proxmox-srvbackup fail
proxmox-srvbackup --traceback fail

# Logging demo
proxmox-srvbackup logdemo
proxmox-srvbackup --set lib_log_rich.console_level=DEBUG logdemo
```

### Entry Points

All commands work with any entry point:

```bash
proxmox-srvbackup backup --dry-run
python -m proxmox_srvbackup backup --dry-run
uvx proxmox_srvbackup backup --dry-run
```

---

## Automated Backups with systemd

Systemd unit files are included for daily automated backups. The service
automatically upgrades `proxmox_srvbackup` to the latest PyPI version
before each run. If the network is unavailable, the existing installation
is used as-is.

### Install the timer

```bash
# 1. Copy service and timer units
sudo cp src/proxmox_srvbackup/adapters/config/systemd/proxmox-srvbackup.service /etc/systemd/system/
sudo cp src/proxmox_srvbackup/adapters/config/systemd/proxmox-srvbackup.timer /etc/systemd/system/

# 2. Reload systemd, enable and start the timer
sudo systemctl daemon-reload
sudo systemctl enable --now proxmox-srvbackup.timer

# 3. Verify the timer is active
sudo systemctl list-timers proxmox-srvbackup.timer
```

### What happens on each timer trigger

1. `ExecStartPre` runs three preparation steps (all non-fatal, prefixed
   with `-`):
   - `uv tool upgrade proxmox_srvbackup` — pull latest version from PyPI
   - `config-deploy --target app --force` — deploy updated default config
     files (your `99-myconfig.toml` is never overwritten)
   - `setup-keys` — generate and deploy SSH keys for any newly added servers
2. `ExecStart` runs `proxmox-srvbackup backup`, which connects to all
   configured servers, pulls backups, applies retention, and sends the
   summary email (if configured).

### Timer schedule

The default timer runs daily at 04:30 with up to 5 minutes of random delay:

```ini
[Timer]
OnCalendar=*-*-* 04:30:00
Persistent=true
RandomizedDelaySec=300
```

### Manual trigger

```bash
sudo systemctl start proxmox-srvbackup.service
journalctl -u proxmox-srvbackup.service -f
```

### Logs

```bash
# Follow live logs
journalctl -u proxmox-srvbackup -f

# Show logs from the last run
journalctl -u proxmox-srvbackup --since today
```

---

## Email Configuration

Email notifications are **disabled by default**. The default configuration ships
with `smtp_hosts = []` and `from_address = ""`, so no email is sent. Backups run
normally without email -- if email is not configured, the notification step is
silently skipped and the backup still succeeds.

To enable notifications, configure at least `smtp_hosts` and `from_address` via
environment variables, `.env` file, or TOML configuration:

**Environment Variables:**

```bash
export PROXMOX_SRVBACKUP___EMAIL__SMTP_HOSTS="smtp.gmail.com:587"
export PROXMOX_SRVBACKUP___EMAIL__FROM_ADDRESS="alerts@example.com"
export PROXMOX_SRVBACKUP___EMAIL__SMTP_USERNAME="your-email@gmail.com"
export PROXMOX_SRVBACKUP___EMAIL__SMTP_PASSWORD="your-app-password"
```

**Configuration File** (add to your `99-myconfig.toml`):

```toml
[email]
smtp_hosts = ["smtp.gmail.com:587"]
from_address = "alerts@example.com"
smtp_username = "your-email@gmail.com"
smtp_password = "your-app-password"
use_starttls = true
timeout = 60.0
```

For Gmail, create an [App Password](https://support.google.com/accounts/answer/185833) instead of using your account password.

---

## Further Documentation

- [Install Guide](INSTALL.md) -- all supported installation methods
- [Configuration Reference](CONFIG.md) -- layered config system, profiles, environment variables
- [Development Handbook](DEVELOPMENT.md) -- dev setup, make targets, testing
- [Contributor Guide](CONTRIBUTING.md) -- workflow, coding standards, PR checklist
- [Changelog](CHANGELOG.md) -- version history
- [Module Reference](docs/systemdesign/module_reference.md) -- architecture and module design
- [License](LICENSE) -- MIT
