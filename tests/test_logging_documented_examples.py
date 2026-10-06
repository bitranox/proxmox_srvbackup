"""Every ``[lib_log_rich]`` example the shipped files document is a value logging accepts.

``defaultconfig.d/90-logging.toml`` and ``.env.example`` show each logging key as an
environment variable and as a ``.env`` line. A user copies those lines as they stand, and a
value lib_log_rich refuses makes ``backup`` and every other command that reads the
configuration exit 78. Each example is loaded here through the real configuration loader, the
environment one as the shell would pass it (outer single quotes removed) and the ``.env`` one
from a ``.env`` file, and then checked the way the logging setup checks it.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest
from lib_layered_config import read_config

from proxmox_srvbackup import __init__conf__
from proxmox_srvbackup.adapters.config.loader import get_default_config_path
from proxmox_srvbackup.adapters.logging.setup import _build_runtime_config  # pyright: ignore[reportPrivateUsage]

_ROOT = Path(__file__).parent.parent
_SHIPPED = (
    _ROOT / "src" / "proxmox_srvbackup" / "adapters" / "config" / "defaultconfig.d" / "90-logging.toml",
    _ROOT / ".env.example",
)
_PREFIX = __init__conf__.LAYEREDCONF_SLUG.upper().replace("-", "_")
_HOMES = ("HOME", "USERPROFILE", "XDG_CONFIG_HOME", "APPDATA", "LOCALAPPDATA")

#: ``# Environment Variable: PROXMOX_SRVBACKUP___LIB_LOG_RICH__KEY=value``
_ENVIRONMENT_LINE = re.compile(rf"^#\s*Environment Variable:\s*({_PREFIX}___LIB_LOG_RICH__\w+)=(.+?)\s*$")
#: ``# .env: LIB_LOG_RICH__KEY=value`` and the bare commented example ``# LIB_LOG_RICH__KEY=value``;
#: a value can hold spaces (``"bold red"``), and a trailing ``(unquoted)`` is a note, not the value.
_DOTENV_LINE = re.compile(r"^#\s*(?:\.env:\s*)?(LIB_LOG_RICH__\w+=.+?)(?:\s+\(unquoted\))?\s*$")


def _examples() -> tuple[list[tuple[str, str, str]], list[tuple[str, str]]]:
    environment: list[tuple[str, str, str]] = []
    dotenv: list[tuple[str, str]] = []
    for path in _SHIPPED:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            where = f"{path.name}:{number}"
            if match := _ENVIRONMENT_LINE.match(line):
                value = match.group(2)
                if len(value) >= 2 and value[0] == value[-1] == "'":
                    value = value[1:-1]
                environment.append((where, match.group(1), value))
            elif match := _DOTENV_LINE.match(line):
                dotenv.append((where, match.group(1)))
    return environment, dotenv


_ENVIRONMENT_EXAMPLES, _DOTENV_EXAMPLES = _examples()


@pytest.fixture
def isolated_homes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """No user configuration file and no stray prefixed variable can take part in a load."""
    for name in _HOMES:
        monkeypatch.setenv(name, str(tmp_path))
    for name in [name for name in os.environ if name.startswith(_PREFIX)]:
        monkeypatch.delenv(name)
    return tmp_path


def _accepted(*, dotenv_path: Path | None = None) -> None:
    config = read_config(
        vendor=__init__conf__.LAYEREDCONF_VENDOR,
        app=__init__conf__.LAYEREDCONF_APP,
        slug=__init__conf__.LAYEREDCONF_SLUG,
        default_file=get_default_config_path(),
        start_dir=str(dotenv_path.parent) if dotenv_path else None,
        dotenv_path=str(dotenv_path) if dotenv_path else None,
    )
    _build_runtime_config(config)


@pytest.mark.os_agnostic
def test_the_shipped_files_document_examples_for_both_layers() -> None:
    """Guards the parametrized tests below against a pattern that matches nothing."""
    assert len(_ENVIRONMENT_EXAMPLES) >= 20, _ENVIRONMENT_EXAMPLES
    assert len(_DOTENV_EXAMPLES) >= 20, _DOTENV_EXAMPLES


@pytest.mark.os_agnostic
@pytest.mark.parametrize(("where", "name", "value"), _ENVIRONMENT_EXAMPLES, ids=[e[0] for e in _ENVIRONMENT_EXAMPLES])
def test_a_documented_environment_example_is_accepted(
    isolated_homes: Path, monkeypatch: pytest.MonkeyPatch, where: str, name: str, value: str
) -> None:
    monkeypatch.setenv(name, value)

    _accepted()


@pytest.mark.os_agnostic
@pytest.mark.parametrize(("where", "line"), _DOTENV_EXAMPLES, ids=[e[0] for e in _DOTENV_EXAMPLES])
def test_a_documented_dotenv_example_is_accepted(isolated_homes: Path, where: str, line: str) -> None:
    dotenv = isolated_homes / "service.env"
    dotenv.write_text(line + "\n", encoding="utf-8")

    _accepted(dotenv_path=dotenv)
