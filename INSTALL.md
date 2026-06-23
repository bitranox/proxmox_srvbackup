# Installation Guide

> The CLI uses `rich-click` for styled output and `lib_cli_exit_tools` for POSIX exit codes.

This guide covers every supported method to install `proxmox_srvbackup`. Pick the option that matches your workflow.


## We recommend `uv` to install the package

### `uv` = Ultra-fast Python package manager

> lightning-fast replacement for `pip`, `venv`, `pip-tools`, and `poetry`
written in Rust, compatible with PEP 621 (`pyproject.toml`)

### `uvx` = On-demand tool runner

> runs tools temporarily in isolated environments without installing them globally


## Install uv (if not already installed)

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Copy binaries to system PATH (optional, for root installs)
cp /root/.local/bin/uv /usr/local/bin/uv
cp /root/.local/bin/uvx /usr/local/bin/uvx
chmod 755 /usr/local/bin/uv /usr/local/bin/uvx

# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

## One-shot run via uvx (no install needed)

```bash
uvx proxmox_srvbackup@latest --help
uvx proxmox_srvbackup@latest backup --dry-run
```

## Persistent install as CLI tool (recommended for servers)

```bash
# Install latest python (optional, if system python is too old)
install_latest_python_gcc.sh
uv python pin /opt/python-latest/bin/python3

# Install from git (latest development version)
uv tool install --python /opt/python-latest/bin/python3 --from "git+https://github.com/bitranox/proxmox_srvbackup.git" proxmox-srvbackup

# Or install from PyPI (latest release)
uv tool install --python /opt/python-latest/bin/python3 proxmox-srvbackup

# Upgrade to latest
uv tool upgrade proxmox-srvbackup
```

## Simpler install (if system python is already 3.10+)

```bash
# Install the CLI tool (isolated environment, added to PATH)
uv tool install proxmox_srvbackup

# Upgrade to latest
uv tool upgrade proxmox_srvbackup
```

## Install as project dependency

```bash
uv venv && source .venv/bin/activate   # Windows: .venv\Scripts\Activate.ps1
uv pip install proxmox_srvbackup
```

## Verify installation

After any install method, confirm the CLI is available:

```bash
proxmox-srvbackup --version
proxmox-srvbackup info
proxmox-srvbackup backup --dry-run
```

---

## Installation via pip

```bash
# optional, install in a venv (recommended)
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
# install from PyPI
pip install proxmox_srvbackup
# optional install from GitHub
pip install "git+https://github.com/bitranox/proxmox_srvbackup"
# optional development install from local
pip install -e ".[dev]"
# optional install from local runtime only:
pip install .
```

## Per-User Installation (No Virtualenv) - from local

```bash
# install from PyPI
pip install --user proxmox_srvbackup
# optional install from GitHub
pip install --user "git+https://github.com/bitranox/proxmox_srvbackup"
# optional install from local
pip install --user .
```

> Note: This respects PEP 668. Avoid using it on system Python builds marked as
> "externally managed". Ensure `~/.local/bin` (POSIX) is on your PATH so the CLI is available.

## pipx (Isolated CLI-Friendly Environment)

```bash
# install pipx via pip
python -m pip install pipx
# optional install pipx via apt
sudo apt install python-pipx
# install via pipx from PyPI
pipx install proxmox_srvbackup
# optional install via pipx from GitHub
pipx install "git+https://github.com/bitranox/proxmox_srvbackup"
# optional install from local
pipx install .
pipx upgrade proxmox_srvbackup
# install from Git tag
pipx install "git+https://github.com/bitranox/proxmox_srvbackup@v1.5.2"
```

## From Build Artifacts

```bash
python -m build
pip install dist/proxmox_srvbackup-*.whl
pip install dist/proxmox_srvbackup-*.tar.gz   # sdist
```

## Poetry or PDM Managed Environments

```bash
# Poetry
poetry add proxmox_srvbackup     # as dependency
poetry install                          # for local dev

# PDM
pdm add proxmox_srvbackup
pdm install
```

## Install Directly from Git

```bash
pip install "git+https://github.com/bitranox/proxmox_srvbackup"
```

## System Package Managers (Optional Distribution Channels)

- Use [fpm](https://fpm.readthedocs.io/) to repackage the Python wheel into `.deb` or `.rpm` for distribution via `apt` or `yum`/`dnf`.

All methods register both the `proxmox_srvbackup` and
`proxmox-srvbackup` commands on your PATH.

---

## Post-Installation Setup

After installing, complete the initial setup:

```bash
# 1. Deploy default configuration (system-wide, requires root)
sudo proxmox-srvbackup config-deploy --target app --force
# Create a 99-myconfig.toml to override defaults instead of editing them directly,
# otherwise updates might overwrite your config!

# 2. Edit 99-myconfig.toml to add your Proxmox servers
#    Linux: /etc/xdg/proxmox-srvbackup/99-myconfig.toml

# 3. Generate and deploy SSH keys
proxmox-srvbackup setup-keys

# 4. Verify with a dry run
proxmox-srvbackup backup --dry-run

# 5. (Optional) Install the systemd timer for daily backups
sudo cp src/proxmox_srvbackup/adapters/config/systemd/proxmox-srvbackup.service /etc/systemd/system/
sudo cp src/proxmox_srvbackup/adapters/config/systemd/proxmox-srvbackup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now proxmox-srvbackup.timer
```
