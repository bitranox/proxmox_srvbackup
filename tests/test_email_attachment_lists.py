"""A list-typed email setting given in a form it cannot be read in is refused, never dropped.

The attachment allow and block lists are security settings: when one is not configured,
btx_lib_mail applies its own defaults. A value in the wrong form must therefore fail
validation; read as "not configured", it would quietly swap the configured list for the
library's defaults. The case that matters is an environment variable: lib_layered_config
reads a JSON array (``[".pdf", ".txt"]``) as a list, while a comma-separated value
(``.pdf,.txt``) stays a string.

``smtp_hosts`` and ``recipients`` read a single string as a one-element list; a value of any
other shape is left for pydantic to accept or refuse rather than emptied.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from pydantic import ValidationError

from proxmox_srvbackup import __init__conf__
from proxmox_srvbackup.adapters import cli as cli_mod
from proxmox_srvbackup.adapters.email.config import EmailConfig, load_email_config_from_dict
from proxmox_srvbackup.composition import build_production

if TYPE_CHECKING:
    from collections.abc import Callable

    from click.testing import CliRunner
    from conftest import EmailCliContext
    from lib_layered_config import Config

VALID = {"smtp_hosts": ["smtp.example.com:587"], "from_address": "sender@example.com"}
SEND_EMAIL = ["send-email", "--to", "recipient@example.com", "--subject", "s", "--body", "b"]

#: The four list settings, by the name the user writes under [email.attachments].
LIST_SETTINGS = ["allowed_extensions", "blocked_extensions", "allowed_directories", "blocked_directories"]
COMMA_VALUE = {
    "allowed_extensions": ".pdf,.txt",
    "blocked_extensions": ".exe,.bat",
    "allowed_directories": "/var/outbox,/var/reports",
    "blocked_directories": "/etc,/root",
}


def _field(setting: str) -> str:
    return f"attachment_{setting}"


def _problems(error: ValidationError) -> list[tuple[str, str]]:
    """Return ``(field, reason)`` per problem; the reason is the validator's own message."""
    problems: list[tuple[str, str]] = []
    for item in error.errors(include_url=False, include_input=False):
        # pydantic prefixes a validator's ValueError message with "Value error, "; the exception
        # it carries holds the message as written.
        raised = item.get("ctx", {}).get("error")
        reason = str(raised) if isinstance(raised, ValueError) else item["msg"]
        problems.append((".".join(str(part) for part in item["loc"]), reason))
    return problems


def _refusal(setting: str, value: object) -> list[tuple[str, str]]:
    with pytest.raises(ValidationError) as caught:
        load_email_config_from_dict({"email": {**VALID, "attachments": {setting: value}}})
    return _problems(caught.value)


# ----------------------------------------------------------------------- the model


@pytest.mark.os_agnostic
@pytest.mark.parametrize("setting", LIST_SETTINGS)
def test_a_comma_separated_string_is_refused_not_dropped(setting: str) -> None:
    problems = _refusal(setting, COMMA_VALUE[setting])

    assert len(problems) == 1, problems
    assert problems[0][0] == _field(setting), problems
    assert "JSON array" in problems[0][1], problems


@pytest.mark.os_agnostic
@pytest.mark.parametrize("setting", LIST_SETTINGS)
def test_a_single_string_is_refused_too(setting: str) -> None:
    """One extension or directory is still a list of one; a bare string is not read as one."""
    problems = _refusal(setting, ".pdf" if "extensions" in setting else "/var/outbox")

    assert [field for field, _ in problems] == [_field(setting)]


@pytest.mark.os_agnostic
@pytest.mark.parametrize("setting", LIST_SETTINGS)
@pytest.mark.parametrize("value", [7, True, {"a": 1}], ids=["int", "bool", "dict"])
def test_a_value_of_another_type_is_refused(setting: str, value: object) -> None:
    assert [field for field, _ in _refusal(setting, value)] == [_field(setting)]


@pytest.mark.os_agnostic
@pytest.mark.parametrize("setting", LIST_SETTINGS)
@pytest.mark.parametrize("value", ["", "   ", []], ids=["empty", "whitespace", "empty-list"])
def test_an_empty_value_means_not_configured(setting: str, value: object) -> None:
    """Like an empty TOML array, an empty environment value leaves the library defaults."""
    config = load_email_config_from_dict({"email": {**VALID, "attachments": {setting: value}}})

    assert getattr(config, _field(setting)) is None


@pytest.mark.os_agnostic
def test_a_list_tuple_or_set_is_read_as_a_frozenset() -> None:
    config = EmailConfig.model_validate(
        {
            "attachment_allowed_extensions": [".pdf", ".txt"],
            "attachment_blocked_extensions": (".exe",),
            "attachment_allowed_directories": {"/var/outbox"},
            "attachment_blocked_directories": frozenset({Path("/etc")}),
        }
    )

    assert config.attachment_allowed_extensions == frozenset({".pdf", ".txt"})
    assert config.attachment_blocked_extensions == frozenset({".exe"})
    assert config.attachment_allowed_directories == frozenset({Path("/var/outbox")})
    assert config.attachment_blocked_directories == frozenset({Path("/etc")})


@pytest.mark.os_agnostic
def test_an_empty_set_still_disables_the_list() -> None:
    """A set is an explicit choice from Python code, so an empty one is kept, not defaulted."""
    config = EmailConfig.model_validate(
        {"attachment_blocked_extensions": set(), "attachment_blocked_directories": set()}
    )

    assert config.attachment_blocked_extensions == frozenset()
    assert config.attachment_blocked_directories == frozenset()


@pytest.mark.os_agnostic
@pytest.mark.parametrize("field", ["smtp_hosts", "recipients"])
def test_a_tuple_of_hosts_or_recipients_is_kept(field: str) -> None:
    value = ("smtp.example.com:587",) if field == "smtp_hosts" else ("a@example.com",)

    assert getattr(EmailConfig.model_validate({field: value}), field) == list(value)


@pytest.mark.os_agnostic
@pytest.mark.parametrize("field", ["smtp_hosts", "recipients"])
def test_a_host_or_recipient_list_of_another_type_is_refused(field: str) -> None:
    with pytest.raises(ValidationError) as caught:
        EmailConfig.model_validate({field: 587})

    assert [name for name, _ in _problems(caught.value)] == [field]


# ----------------------------------------------------------------------- the real loader


def _set_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, setting: str, value: str) -> Config:
    prefix = __init__conf__.LAYEREDCONF_SLUG.upper().replace("-", "_")
    monkeypatch.setenv(f"{prefix}___EMAIL__ATTACHMENTS__{setting.upper()}", value)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    return build_production().get_config(dotenv_path=str(tmp_path / "absent.env"))


@pytest.mark.os_agnostic
@pytest.mark.parametrize("setting", LIST_SETTINGS)
def test_a_comma_separated_environment_value_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, clear_config_cache: None, setting: str
) -> None:
    config = _set_env(monkeypatch, tmp_path, setting, COMMA_VALUE[setting])

    assert config.get("email", {}).get("attachments", {}).get(setting) == COMMA_VALUE[setting]
    with pytest.raises(ValidationError):
        load_email_config_from_dict(config.as_dict())


@pytest.mark.os_agnostic
@pytest.mark.parametrize("setting", LIST_SETTINGS)
def test_a_json_array_environment_value_loads(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, clear_config_cache: None, setting: str
) -> None:
    """Control: the form the refusal names is the one that works."""
    items = COMMA_VALUE[setting].split(",")
    config = _set_env(monkeypatch, tmp_path, setting, "[" + ", ".join(f'"{item}"' for item in items) + "]")

    loaded = getattr(load_email_config_from_dict(config.as_dict()), _field(setting))

    expected = frozenset(Path(item) for item in items) if "directories" in setting else frozenset(items)
    assert loaded == expected


# ----------------------------------------------------------------------- the command


@pytest.mark.os_agnostic
def test_send_email_refuses_a_comma_separated_list_and_sends_nothing(
    cli_runner: CliRunner, email_cli_context: Callable[[dict[str, Any]], EmailCliContext]
) -> None:
    ctx = email_cli_context({**VALID, "attachments": {"blocked_extensions": ".exe,.bat"}})
    # The fixture's in-memory loader skips the [email.attachments] flattening; the real one is
    # what reads the setting this test is about.
    services = dataclasses.replace(ctx.factory(), load_email_config_from_dict=load_email_config_from_dict)

    result = cli_runner.invoke(cli_mod.cli, SEND_EMAIL, obj=lambda: services)

    assert result.exit_code != 0, result.output
    assert isinstance(result.exception, ValidationError), result.exception
    assert "attachment_blocked_extensions" in str(result.exception)
    assert ctx.spy.sent_emails == []
