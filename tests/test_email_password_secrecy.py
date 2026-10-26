"""The SMTP password never reaches an error message, the console or the log.

pydantic prints the input it refused: the offending value for a field error, and the whole
input mapping (truncated, so whether the password shows depends on key order) for a
model-level one. ``EmailConfig`` therefore hides its input in errors, and its password
validator refuses without naming the value. Every password below is a planted dummy; the
check looks for any 4-character piece of it, so a truncated echo counts as a leak.

Three shapes a real password takes are accepted, not refused: an all-digit password, which
lib_layered_config's environment layer turns into an integer, a ``SecretStr``, and a non-ASCII
password, which btx_lib_mail sends with UTF-8 AUTH PLAIN. A password typed under a key the
section does not know is refused as an unknown key, and its value is never shown.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import re
from typing import TYPE_CHECKING, Any

import lib_log_rich.runtime
import pytest
from lib_layered_config import Config
from lib_log_rich.domain import LogLevel
from pydantic import SecretStr, ValidationError

from proxmox_srvbackup import __init__conf__
from proxmox_srvbackup.adapters import cli as cli_mod
from proxmox_srvbackup.adapters.cli.main import main
from proxmox_srvbackup.adapters.email.config import EmailConfig, load_email_config_from_dict
from proxmox_srvbackup.adapters.memory.email import EmailSpy
from proxmox_srvbackup.composition import AppServices, build_production, build_testing

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

    from click.testing import CliRunner

#: Planted dummies, not credentials.
DUMMY = "Qz7vXk2mWp9R"
DIGITS = "98979695"
NON_ASCII = "Qz7vXk2m\u00e9Wp9R"

SEND_EMAIL = ["send-email", "--to", "recipient@example.com", "--subject", "s", "--body", "b"]
VALID = {"smtp_hosts": ["smtp.example.com:587"], "from_address": "sender@example.com"}

#: Text that varies per run and could hold any four digits: ISO timestamps, 32-digit hex event
#: ids, process ids and traceback line numbers. Removed before looking for a digit dummy.
_NOISE = re.compile(
    r"\d{4}-\d\d-\d\dT[\d:.+-]+|\b[0-9a-f]{32}\b"
    r'|process_id\w*"?\s*[:=]\s*(?:\[[\d,\s]*\]|\d+)|process_id\S*'
    r"|line \d+|\[\d\d:\d\d:\d\d\]|0x[0-9a-f]+"
)


def _pieces(dummy: str) -> list[str]:
    return [dummy[i : i + 4] for i in range(len(dummy) - 3)]


def _leaked(dummy: str, text: str) -> list[str]:
    cleaned = _NOISE.sub("", text)
    return [piece for piece in _pieces(dummy) if piece in cleaned]


@pytest.mark.os_agnostic
def test_the_leak_check_can_fail() -> None:
    """Control: the instrument finds a truncated echo, and the noise filter keeps a real one."""
    assert _leaked(DUMMY, "input_value={'smtp_password': 'Qz7vXk...'}") == ["Qz7v", "z7vX", "7vXk"]
    assert _leaked(DIGITS, "2026-09-28T15:26:59.989796+00:00 password=98979695") != []


@pytest.mark.os_agnostic
def test_a_process_id_value_is_noise_however_the_log_writes_it() -> None:
    """A PID holding a piece of the digit dummy must not read as a leak, in either JSON field."""
    assert _leaked(DIGITS, '{"process_id": 19695, "process_id_chain": [197969, 1]}') == []
    assert _leaked(DIGITS, "process_id=19695") == []
    assert _leaked(DIGITS, '{"process_id": 1, "password": "98979695"}') != []


# ----------------------------------------------------------------------- the model


@pytest.mark.os_agnostic
def test_an_all_digit_password_is_read_as_its_digits() -> None:
    config = EmailConfig.model_validate({"smtp_password": int(DIGITS)})

    assert config.smtp_password == SecretStr(DIGITS)


@pytest.mark.os_agnostic
def test_an_all_digit_password_from_the_environment_loads(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, clear_config_cache: None
) -> None:
    """Through the real loader: the environment layer turns the digits into an int."""
    prefix = __init__conf__.LAYEREDCONF_SLUG.upper().replace("-", "_")
    monkeypatch.setenv(f"{prefix}___EMAIL__SMTP_PASSWORD", DIGITS)
    config = build_production().get_config(dotenv_path=str(tmp_path / "absent.env"))

    assert config.get("email", {}).get("smtp_password") == int(DIGITS)
    assert load_email_config_from_dict(config.as_dict()).smtp_password == SecretStr(DIGITS)


@pytest.mark.os_agnostic
@pytest.mark.parametrize(
    "value",
    [[DUMMY], {"secret": DUMMY}, True, 1.5],
    ids=["list", "dict", "bool", "float"],
)
def test_a_password_of_another_type_is_refused_without_its_value(value: object) -> None:
    with pytest.raises(ValidationError) as caught:
        load_email_config_from_dict({"email": {**VALID, "smtp_password": value}})

    text = f"{caught.value}\n{caught.value!r}"
    assert "smtp_password" in text
    assert _leaked(DUMMY, text) == []


@pytest.mark.os_agnostic
@pytest.mark.parametrize(
    ("password", "dummy"),
    [(DUMMY, DUMMY), (int(DIGITS), DIGITS), (SecretStr(DUMMY), DUMMY)],
    ids=["string", "integer", "secretstr"],
)
def test_a_model_level_error_does_not_show_the_password(password: object, dummy: str) -> None:
    """A model-level error's input is the whole mapping, password included.

    ConfMail's empty-blocklist check runs on the whole model: an empty blocked set from Python
    with no allowlist and no opt-in. A field error (a negative timeout) would not do: its input
    is only the field's own value.
    """
    with pytest.raises(ValidationError) as caught:
        EmailConfig.model_validate({"smtp_password": password, "attachment_blocked_extensions": set()})

    assert [item["loc"] for item in caught.value.errors()] == [()], "control: the error is model-level"
    text = f"{caught.value}\n{caught.value!r}\n{caught.value.errors()}\n{caught.value.json()}"
    assert _leaked(dummy, text) == []


@pytest.mark.os_agnostic
@pytest.mark.parametrize(
    ("password", "dummy"),
    [(DUMMY, DUMMY), (int(DIGITS), DIGITS), (SecretStr(DUMMY), DUMMY)],
    ids=["string", "integer", "secretstr"],
)
def test_a_field_error_next_to_the_password_does_not_show_it(password: object, dummy: str) -> None:
    with pytest.raises(ValidationError) as caught:
        load_email_config_from_dict({"email": {"smtp_password": password, "timeout": -5}})

    text = f"{caught.value}\n{caught.value!r}"
    # The raw pydantic text names the field; only describe_validation_error rewrites it.
    assert "smtp_timeout must be positive" in text
    assert _leaked(dummy, text) == []


@pytest.mark.os_agnostic
@pytest.mark.parametrize(
    "fields",
    [{"smtp_password": NON_ASCII}, {"smtp_username": NON_ASCII}],
    ids=["password", "username"],
)
def test_a_non_ascii_credential_is_accepted_as_written(fields: dict[str, object]) -> None:
    """btx_lib_mail logs in with UTF-8 AUTH PLAIN, so a non-ASCII credential is valid."""
    config = load_email_config_from_dict({"email": {**VALID, **fields}})

    password = config.smtp_password.get_secret_value() if config.smtp_password else None
    assert NON_ASCII in (password, config.smtp_username)


@pytest.mark.os_agnostic
def test_a_non_ascii_password_from_the_file_reaches_the_send(cli_runner: CliRunner) -> None:
    spy = EmailSpy()
    result = cli_runner.invoke(
        cli_mod.cli, SEND_EMAIL, obj=_services({**VALID, "smtp_username": "u", "smtp_password": NON_ASCII}, spy)
    )

    assert result.exit_code == 0, result.output
    sent = spy.sent_emails[0].config.smtp_password
    assert sent is not None
    assert sent.get_secret_value() == NON_ASCII


@pytest.mark.os_agnostic
def test_an_ascii_password_with_punctuation_is_kept_as_written() -> None:
    config = EmailConfig.model_validate({"smtp_password": " p@ss w0rd!~ "})

    assert config.smtp_password == SecretStr(" p@ss w0rd!~ ")


# ------------------------------------------------------------------------- the CLI


def _services(email: dict[str, Any], spy: EmailSpy | None = None) -> Callable[[], AppServices]:
    config = Config({"email": email}, {})

    def get_config(**_kwargs: Any) -> Config:
        return config

    def build() -> AppServices:
        services = dataclasses.replace(build_testing(), get_config=get_config)
        if spy is None:
            return services
        return dataclasses.replace(services, send_email=spy.send_email)

    return build


@dataclasses.dataclass(frozen=True)
class Refusal:
    """An email configuration the command refuses, and the dummy password it carries."""

    email: dict[str, Any]
    options: list[str]
    dummy: str


#: Refused while reading the configuration file.
REFUSED_IN_FILE: dict[str, Refusal] = {
    "integer-in-file": Refusal({**VALID, "smtp_password": int(DIGITS), "timeout": -5}, [], DIGITS),
    "list-in-file": Refusal({**VALID, "smtp_password": [DUMMY]}, [], DUMMY),
    "string-in-file-invalid-sibling": Refusal({"smtp_password": DUMMY, "smtp_hosts": ["bad host:x"]}, [], DUMMY),
    "password-under-an-unknown-key": Refusal({**VALID, "smtp_pasword": DUMMY}, [], DUMMY),
}
#: Refused while applying the command-line options.
REFUSED_BY_OPTION: dict[str, Refusal] = {
    "option-invalid-sibling": Refusal(VALID, ["--smtp-password", DUMMY, "--timeout", "-5"], DUMMY),
}
REFUSED = {**REFUSED_IN_FILE, **REFUSED_BY_OPTION}


@pytest.mark.os_agnostic
@pytest.mark.parametrize("traceback", [[], ["--traceback"]], ids=["plain", "traceback"])
@pytest.mark.parametrize("case", REFUSED.values(), ids=REFUSED.keys())
def test_a_refused_email_configuration_does_not_print_the_password(
    capsys: pytest.CaptureFixture[str], managed_traceback_state: None, traceback: list[str], case: Refusal
) -> None:
    """Through ``main()``, whose catch-all prints whatever escapes a command."""
    exit_code = main([*traceback, *SEND_EMAIL, *case.options], services_factory=_services(case.email))

    captured = capsys.readouterr()
    assert exit_code != 0
    assert _leaked(case.dummy, captured.out + captured.err) == []


@pytest.mark.os_agnostic
def test_the_password_option_reaches_the_model(cli_runner: CliRunner) -> None:
    """Control: the channel the refusal tests use does carry the password into the model."""
    spy = EmailSpy()
    result = cli_runner.invoke(cli_mod.cli, [*SEND_EMAIL, "--smtp-password", DUMMY], obj=_services(VALID, spy))

    assert result.exit_code == 0, result.output
    password = spy.sent_emails[0].config.smtp_password
    assert password is not None
    assert password.get_secret_value() == DUMMY


@pytest.fixture
def recorded_log() -> Iterator[Callable[[], str]]:
    """A lib_log_rich runtime that keeps every event, stdlib logging included, for a dump."""
    lib_log_rich.runtime.init(
        lib_log_rich.runtime.RuntimeConfig(
            service="password-secrecy-test",
            environment="test",
            console_level=LogLevel.CRITICAL,
            backend_level=LogLevel.DEBUG,
            enable_journald=False,
            enable_eventlog=False,
            enable_graylog=False,
            queue_enabled=False,
        )
    )
    lib_log_rich.runtime.attach_std_logging(logger_level=logging.DEBUG)

    def dump() -> str:
        return json.dumps(json.loads(lib_log_rich.runtime.dump(dump_format="json")))

    yield dump
    lib_log_rich.runtime.shutdown()


@pytest.mark.os_agnostic
@pytest.mark.parametrize("case", REFUSED.values(), ids=REFUSED.keys())
def test_a_refused_email_configuration_does_not_log_the_password(
    cli_runner: CliRunner, recorded_log: Callable[[], str], case: Refusal
) -> None:
    result = cli_runner.invoke(cli_mod.cli, [*SEND_EMAIL, *case.options], obj=_services(case.email))

    dump = recorded_log()
    assert result.exit_code != 0
    assert "cli-send-email" in dump, "control: the refusal was logged inside the command's job"
    assert _leaked(case.dummy, dump) == []
