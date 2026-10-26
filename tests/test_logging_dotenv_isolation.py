"""What the logging setup takes from a ``.env``, and what an invalid logging section does.

Logging reads lib_log_rich's own ``LOG_*`` variables from a ``.env``. Nothing else in that file may
reach the process environment: a later configuration load (``config --profile``, the deploy's
permission read) would take an app-prefixed line for the environment layer. With ``--env-file``,
that file is the only ``.env`` read. An invalid ``[lib_log_rich]`` section is a configuration
failure like a broken file: the commands that read the configuration refuse with exit 78, the
others still run, logging with its defaults and every valid ``LOG_*`` variable. A refused ``LOG_*``
variable, from the environment or the ``.env``, is the same failure: logging still starts, with its
defaults and without any ``LOG_*`` variable.

The end-to-end tests run the real CLI in a subprocess with every configuration location under
``tmp_path``.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import lib_log_rich.runtime
import pytest
from conftest import SYSTEM_LAYER_ROOT_VARIABLES
from lib_layered_config import Config

from proxmox_srvbackup import __init__conf__
from proxmox_srvbackup.adapters.logging.setup import (
    InvalidLoggingConfigError,
    check_logging_config,
    init_logging,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

PREFIX = __init__conf__.LAYEREDCONF_SLUG.upper().replace("-", "_")
_HOMES = ("HOME", "USERPROFILE", "XDG_CONFIG_HOME", "APPDATA", "LOCALAPPDATA")


def _inherited(name: str) -> bool:
    """Keep the system-layer redirect the autouse fixture set; drop the developer's own config variables."""
    return name in SYSTEM_LAYER_ROOT_VARIABLES or not name.startswith((PREFIX, "LOG_", "LIB_LAYERED_CONFIG"))


def _run(cwd: Path, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    clean = {k: v for k, v in os.environ.items() if _inherited(k)}
    clean.update(dict.fromkeys(_HOMES, str(cwd)))
    clean.update(env or {})
    return subprocess.run(
        [sys.executable, "-m", "proxmox_srvbackup", *args],
        cwd=cwd,
        env=clean,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


@pytest.fixture
def log_variables() -> Iterator[list[str]]:
    """Names a test lets ``init_logging`` set; each is removed from the environment afterwards."""
    names: list[str] = []
    yield names
    for name in names:
        os.environ.pop(name, None)


# ------------------------------------------------------------------ only LOG_* reaches the environment


@pytest.mark.os_agnostic
def test_only_log_variables_from_the_dotenv_reach_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, log_variables: list[str]
) -> None:
    app_key = f"{PREFIX}___EMAIL__FROM_ADDRESS"
    log_variables.extend(["LOG_DOTENV_PROBE", app_key])
    (tmp_path / ".env").write_text(f"{app_key}=leaked@example.com\nLOG_DOTENV_PROBE=from-dotenv\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(app_key, raising=False)

    init_logging(Config({}, {}))

    assert os.environ.get("LOG_DOTENV_PROBE") == "from-dotenv"
    assert app_key not in os.environ


@pytest.mark.os_agnostic
def test_an_explicit_env_file_is_the_only_dotenv_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, log_variables: list[str]
) -> None:
    log_variables.extend(["LOG_FROM_CWD", "LOG_FROM_EXPLICIT"])
    (tmp_path / ".env").write_text("LOG_FROM_CWD=cwd\n", encoding="utf-8")
    explicit = tmp_path / "explicit.env"
    explicit.write_text("LOG_FROM_EXPLICIT=explicit\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    init_logging(Config({}, {}), dotenv_path=str(explicit))

    assert os.environ.get("LOG_FROM_EXPLICIT") == "explicit"
    assert "LOG_FROM_CWD" not in os.environ


@pytest.mark.os_agnostic
def test_a_dotenv_never_replaces_a_variable_already_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, log_variables: list[str]
) -> None:
    log_variables.append("LOG_ALREADY_SET")
    monkeypatch.setenv("LOG_ALREADY_SET", "from-environment")
    (tmp_path / ".env").write_text("LOG_ALREADY_SET=from-dotenv\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    init_logging(Config({}, {}))

    assert os.environ["LOG_ALREADY_SET"] == "from-environment"


@pytest.mark.os_agnostic
def test_a_dotenv_that_is_not_utf8_does_not_stop_logging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, log_variables: list[str]
) -> None:
    """The loader already reports such a file as a configuration failure; logging must still start."""
    log_variables.append("LOG_AFTER_BAD_BYTES")
    (tmp_path / ".env").write_bytes(b"LOG_AFTER_BAD_BYTES=x\nNAME=\xff\xfe\n")
    monkeypatch.chdir(tmp_path)

    init_logging(Config({}, {}))

    assert lib_log_rich.runtime.is_initialised()


# ------------------------------------------------------------------ end to end: a .env cannot reach a reload


@pytest.mark.os_agnostic
def test_a_prefixed_line_in_the_cwd_dotenv_does_not_reach_a_profile_reload(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text(f"{PREFIX}___EMAIL__FROM_ADDRESS=leaked@example.com\n", encoding="utf-8")

    result = _run(tmp_path, "config", "--profile", "production", "--format", "json", "--section", "email")

    assert result.returncode == 0, result.stderr
    assert "leaked@example.com" not in result.stdout


@pytest.mark.os_agnostic
def test_a_prefixed_permission_line_in_the_cwd_dotenv_does_not_block_a_deploy(tmp_path: Path) -> None:
    key = f"{PREFIX}___LIB_LAYERED_CONFIG__DEFAULT_PERMISSIONS__USER_FILE"
    (tmp_path / ".env").write_text(f"{key}=400\n", encoding="utf-8")

    result = _run(tmp_path, "config-deploy", "--target", "user", "--force")

    assert result.returncode == 0, result.stderr


# ------------------------------------------------------------------ an invalid [lib_log_rich] section


@pytest.mark.os_agnostic
def test_an_invalid_logging_section_leaves_commands_that_do_not_read_the_config_running(tmp_path: Path) -> None:
    result = _run(tmp_path, "hello", env={f"{PREFIX}___LIB_LOG_RICH__RATE_LIMIT": "100:60"})

    assert result.returncode == 0, result.stderr
    assert "Hello World" in result.stdout


@pytest.mark.os_agnostic
def test_an_invalid_logging_section_is_a_configuration_error_naming_the_key(tmp_path: Path) -> None:
    result = _run(tmp_path, "config", env={f"{PREFIX}___LIB_LOG_RICH__RATE_LIMIT": "100:60"})

    assert result.returncode == 78
    errors = [line for line in result.stderr.splitlines() if line.startswith("Error:")]
    assert len(errors) == 1, result.stderr
    assert "lib_log_rich.rate_limit" in errors[0]
    assert "pydantic.dev" not in result.stderr
    assert "100:60" not in result.stderr


@pytest.mark.os_agnostic
def test_each_refused_logging_setting_gets_its_own_line(tmp_path: Path) -> None:
    env = {f"{PREFIX}___LIB_LOG_RICH__RATE_LIMIT": "100:60", f"{PREFIX}___LIB_LOG_RICH__RING_BUFFER_SIZE": "abc"}

    result = _run(tmp_path, "config", env=env)

    errors = [line for line in result.stderr.splitlines() if line.startswith("Error:")]
    assert result.returncode == 78
    assert sorted(e.split(":", 2)[1].strip() for e in errors) == [
        "lib_log_rich.rate_limit",
        "lib_log_rich.ring_buffer_size",
    ]


@pytest.mark.os_agnostic
def test_a_value_only_lib_log_rich_itself_refuses_is_a_configuration_error_too(tmp_path: Path) -> None:
    """``queue_maxsize = 0`` passes the type check and is refused by lib_log_rich's own range check."""
    env = {f"{PREFIX}___LIB_LOG_RICH__QUEUE_MAXSIZE": "0"}

    refused = _run(tmp_path, "config", env=env)
    running = _run(tmp_path, "hello", env=env)

    assert refused.returncode == 78
    assert "lib_log_rich.queue_maxsize" in refused.stderr
    assert "pydantic.dev" not in refused.stderr
    assert running.returncode == 0, running.stderr


@pytest.mark.os_agnostic
def test_an_invalid_logging_section_does_not_block_the_deploy_that_replaces_it(tmp_path: Path) -> None:
    result = _run(
        tmp_path, "config-deploy", "--target", "user", "--force", env={f"{PREFIX}___LIB_LOG_RICH__RATE_LIMIT": "100:60"}
    )

    assert result.returncode == 0, result.stderr


# ------------------------------------------------------------------ config --profile reloads, and checks logging too

#: One refused setting of each kind lib_log_rich has: the section's type check, its own range
#: check, a ``LOG_*`` value its settings resolution refuses, and the values only starting the
#: runtime refuses - a level name (in the section or a ``LOG_*`` variable), a scrub pattern, a
#: console format preset and a console style key.
_REFUSED_LOGGING = {
    "type": {f"{PREFIX}___LIB_LOG_RICH__RATE_LIMIT": "100:60"},
    "range": {f"{PREFIX}___LIB_LOG_RICH__QUEUE_MAXSIZE": "0"},
    "settings-variable": {"LOG_RATE_LIMIT": "bogus"},
    "section-level": {f"{PREFIX}___LIB_LOG_RICH__CONSOLE_LEVEL": "bogus"},
    "log-variable": {"LOG_CONSOLE_LEVEL": "bogus"},
    "scrub-pattern": {"LOG_SCRUB_PATTERNS": "token=("},
    "console-preset": {"LOG_CONSOLE_FORMAT_PRESET": "bogus"},
    "console-style": {"LOG_CONSOLE_STYLES": "bogus=red"},
}


def _error_lines(result: subprocess.CompletedProcess[str]) -> list[str]:
    return [line for line in result.stderr.splitlines() if line.startswith("Error:")]


@pytest.mark.os_agnostic
@pytest.mark.parametrize("env", _REFUSED_LOGGING.values(), ids=_REFUSED_LOGGING.keys())
def test_config_with_a_profile_refuses_a_logging_setting_like_config_without_one(
    tmp_path: Path, env: dict[str, str]
) -> None:
    plain = _run(tmp_path, "config", env=env)
    reloaded = _run(tmp_path, "config", "--profile", "production", env=env)

    # Premise: plain config refuses this setting with one line per problem.
    assert plain.returncode == 78, plain.stderr
    assert _error_lines(plain), plain.stderr
    assert reloaded.returncode == 78, reloaded.stderr
    assert _error_lines(reloaded) == _error_lines(plain)


@pytest.mark.os_agnostic
def test_a_logging_section_refused_only_in_the_profile_file_refuses_config_with_that_profile(tmp_path: Path) -> None:
    # The user layer lives in a different place on each OS; the deploy writes it there and says where.
    deployed = _run(tmp_path, "config-deploy", "--target", "user", "--profile", "broken")
    assert deployed.returncode == 0, deployed.stderr
    written = [line.strip()[2:] for line in deployed.stdout.splitlines() if line.strip().startswith("+ ")]
    profile_files = [Path(path) for path in written if Path(path).name == "config.toml"]
    assert len(profile_files) == 1, deployed.stdout
    # config.d merges after config.toml, and the deployed 90-logging.toml sets rate_limit itself.
    (profile_files[0].parent / "config.d" / "99-refused.toml").write_text(
        '[lib_log_rich]\nrate_limit = "100:60"\n', encoding="utf-8"
    )

    plain = _run(tmp_path, "config")
    reloaded = _run(tmp_path, "config", "--profile", "broken")

    assert plain.returncode == 0, plain.stderr
    assert reloaded.returncode == 78, reloaded.stderr
    errors = _error_lines(reloaded)
    assert len(errors) == 1, reloaded.stderr
    assert "lib_log_rich.rate_limit" in errors[0]
    assert "100:60" not in reloaded.stderr


@pytest.mark.os_agnostic
def test_checking_logging_refuses_a_setting_although_logging_already_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    """``init_logging`` returns at once on a running runtime; the check must judge the new settings."""
    init_logging(Config({}, {}))
    # Premise: logging runs, so a plain init_logging would no longer check anything.
    running = lib_log_rich.runtime.current_runtime()
    monkeypatch.setenv("LOG_SCRUB_PATTERNS", "token=(")

    with pytest.raises(InvalidLoggingConfigError, match="Invalid scrub pattern"):
        check_logging_config(Config({}, {}))

    assert lib_log_rich.runtime.current_runtime() is running
    handlers = [h for h in logging.getLogger().handlers if isinstance(h, lib_log_rich.runtime.StdlibLoggingHandler)]
    assert len(handlers) == 1


@pytest.mark.os_agnostic
def test_checking_a_valid_logging_section_leaves_the_running_runtime_alone() -> None:
    """The check never stops or replaces the runtime, so no other thread loses its logging."""
    init_logging(Config({}, {}))
    running = lib_log_rich.runtime.current_runtime()

    check_logging_config(Config({"lib_log_rich": {"console_level": "debug"}}, {}))

    assert lib_log_rich.runtime.current_runtime() is running


def _graylog_section(*, tls: bool) -> dict[str, object]:
    # The endpoint as a TOML file writes it: a [host, port] list, which RuntimeConfig accepts.
    return {
        "enable_graylog": True,
        "graylog_endpoint": ["graylog.invalid", 12201],
        "graylog_protocol": "udp",
        "graylog_tls": tls,
    }


@pytest.mark.os_agnostic
def test_checking_logging_refuses_tls_over_udp_for_graylog() -> None:
    """A refusal no single field owns (TLS with UDP) reaches the check, as one ``lib_log_rich: <reason>`` line."""
    with pytest.raises(InvalidLoggingConfigError, match="TLS is only supported for TCP Graylog transport") as caught:
        check_logging_config(Config({"lib_log_rich": _graylog_section(tls=True)}, {}))

    assert caught.value.problems[0].startswith("lib_log_rich: ")


@pytest.mark.os_agnostic
def test_checking_logging_accepts_graylog_over_udp_without_tls() -> None:
    """Control: the same section without TLS is valid, so the refusal above is the TLS one."""
    check_logging_config(Config({"lib_log_rich": _graylog_section(tls=False)}, {}))


# ------------------------------------------------------------------ a refused setting still leaves logging running


@pytest.mark.os_agnostic
def test_a_refused_logging_section_still_leaves_logging_running() -> None:
    with pytest.raises(InvalidLoggingConfigError):
        init_logging(Config({"lib_log_rich": {"rate_limit": "100:60"}}, {}))

    assert lib_log_rich.runtime.is_initialised()


@pytest.mark.os_agnostic
def test_only_the_first_call_raises_for_a_refused_logging_section() -> None:
    """The fallback leaves logging running, so a later call returns before it checks anything."""
    refused = Config({"lib_log_rich": {"rate_limit": "100:60"}}, {})
    with pytest.raises(InvalidLoggingConfigError):
        init_logging(refused)

    init_logging(refused)

    assert lib_log_rich.runtime.is_initialised()


@pytest.mark.os_agnostic
def test_a_refused_log_variable_still_leaves_logging_running(monkeypatch: pytest.MonkeyPatch) -> None:
    """lib_log_rich reads every ``LOG_*`` variable on each init, so the fallback must start without them."""
    monkeypatch.setenv("LOG_CONSOLE_LEVEL", "bogus")

    with pytest.raises(InvalidLoggingConfigError):
        init_logging(Config({}, {}))

    assert lib_log_rich.runtime.is_initialised()
    assert os.environ["LOG_CONSOLE_LEVEL"] == "bogus"


@pytest.mark.os_agnostic
@pytest.mark.parametrize(
    "command",
    [("info",), ("hello",), ("config-deploy", "--target", "user", "--force")],
    ids=["info", "hello", "deploy"],
)
def test_a_refused_log_variable_in_the_env_file_leaves_commands_that_do_not_read_the_config_running(
    tmp_path: Path, command: tuple[str, ...]
) -> None:
    env_file = tmp_path / "service.env"
    env_file.write_text("LOG_CONSOLE_LEVEL=bogus\n", encoding="utf-8")

    result = _run(tmp_path, "--env-file", str(env_file), *command)

    assert result.returncode == 0, result.stderr


@pytest.mark.os_agnostic
@pytest.mark.parametrize("command", [("config",), ("backup", "--dry-run")], ids=["config", "backup"])
def test_a_refused_log_variable_in_the_env_file_is_a_configuration_error(
    tmp_path: Path, command: tuple[str, ...]
) -> None:
    env_file = tmp_path / "service.env"
    env_file.write_text("LOG_CONSOLE_LEVEL=bogus\n", encoding="utf-8")

    result = _run(tmp_path, "--env-file", str(env_file), *command)

    assert result.returncode == 78, result.stderr
    errors = [line for line in result.stderr.splitlines() if line.startswith("Error:")]
    assert len(errors) == 1, result.stderr
    assert errors[0].startswith("Error: lib_log_rich")


@pytest.mark.os_agnostic
def test_a_refused_log_variable_in_the_environment_leaves_info_running(tmp_path: Path) -> None:
    result = _run(tmp_path, "info", env={"LOG_CONSOLE_LEVEL": "bogus"})

    assert result.returncode == 0, result.stderr


@pytest.mark.os_agnostic
def test_every_log_variable_comes_back_even_when_the_default_start_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """The fallback start hides the ``LOG_*`` variables; a failure there must not lose them.

    ``lib_log_rich.runtime.init`` is the third-party edge: a start that sees the variable refuses
    like a bad level, a start without it fails for a reason of its own.
    """
    monkeypatch.setenv("LOG_CONSOLE_LEVEL", "bogus")
    variable_seen: list[bool] = []

    def refuse(_config: object) -> None:
        variable_seen.append("LOG_CONSOLE_LEVEL" in os.environ)
        if "LOG_CONSOLE_LEVEL" in os.environ:
            raise ValueError("Unknown log level: 'bogus'")
        raise RuntimeError("the default start failed too")

    monkeypatch.setattr(lib_log_rich.runtime, "init", refuse)

    with pytest.raises(RuntimeError, match="the default start failed too"):
        init_logging(Config({}, {}))

    # The configuration, then the defaults with the variables, then the defaults without them.
    assert variable_seen == [True, True, False]
    assert os.environ["LOG_CONSOLE_LEVEL"] == "bogus"


# ------------------------------------------------------------------ which LOG_* variables the fallback keeps

_INFO_LINE = "Displaying package information"
_REFUSED_SECTION = ("--set", "lib_log_rich.rate_limit=100:60")


@pytest.mark.os_agnostic
def test_a_valid_log_variable_is_still_honoured_when_the_logging_section_is_refused(tmp_path: Path) -> None:
    """Only a refused ``LOG_*`` variable is a reason to start without them; a refused section is not."""
    shown = _run(tmp_path, *_REFUSED_SECTION, "info")
    quieted = _run(tmp_path, *_REFUSED_SECTION, "info", env={"LOG_CONSOLE_LEVEL": "error"})

    # Premise: at the default console level the fallback shows info's INFO line.
    assert shown.returncode == 0, shown.stderr
    assert _INFO_LINE in shown.stderr, shown.stderr
    assert quieted.returncode == 0, quieted.stderr
    assert _INFO_LINE not in quieted.stderr, quieted.stderr


@pytest.mark.os_agnostic
@pytest.mark.parametrize("section", [(), _REFUSED_SECTION], ids=["variable-alone", "with-refused-section"])
def test_a_refused_log_variable_is_hidden_and_the_fallback_still_logs(tmp_path: Path, section: tuple[str, ...]) -> None:
    """The defaults start without every ``LOG_*`` variable, and std logging still reaches the console."""
    result = _run(tmp_path, *section, "info", env={"LOG_CONSOLE_LEVEL": "bogus"})

    assert result.returncode == 0, result.stderr
    assert _INFO_LINE in result.stderr, result.stderr


@pytest.mark.os_agnostic
def test_the_subprocess_reads_the_redirected_app_layer_not_the_host_s(
    tmp_path: Path, app_layer_config_file: Path
) -> None:
    """``_run`` keeps the conftest's system-layer redirect while dropping the developer's variables."""
    app_layer_config_file.write_text('[layer_isolation_probe]\nread_from = "redirected app layer"\n', encoding="utf-8")

    result = _run(tmp_path, "config", "--section", "layer_isolation_probe")

    assert result.returncode == 0, result.stderr
    assert "redirected app layer" in result.stdout, result.stdout
