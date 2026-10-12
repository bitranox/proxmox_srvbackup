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
from btx_lib_mail import ConfMail
from lib_layered_config import Config
from pydantic import ValidationError

from proxmox_srvbackup import __init__conf__
from proxmox_srvbackup.adapters.cli.main import main
from proxmox_srvbackup.adapters.email.config import (
    FILE_KEY_TO_FIELD,
    EmailConfig,
    describe_validation_error,
    load_email_config_from_dict,
)
from proxmox_srvbackup.adapters.memory import EmailSpy
from proxmox_srvbackup.composition import AppServices, build_production, build_testing

if TYPE_CHECKING:
    from collections.abc import Callable

VALID = {"smtp_hosts": ["smtp.example.com:587"], "from_address": "sender@example.com"}
SEND_EMAIL = ["send-email", "--to", "recipient@example.com", "--subject", "s", "--body", "b"]

#: The four list settings, by the name the user writes under [email.attachments].
LIST_SETTINGS = ["allowed_extensions", "blocked_extensions", "allowed_directories", "blocked_directories"]
COMMA_VALUE = {
    "allowed_extensions": ".pdf,.txt",
    "blocked_extensions": ".exe,.bat",
    "allowed_directories": "/srv/outbox,/srv/reports",
    "blocked_directories": "/etc,/root",
}


def _field(setting: str) -> str:
    return f"attachment_{setting}"


def _refusal(setting: str, value: object) -> list[str]:
    with pytest.raises(ValidationError) as caught:
        load_email_config_from_dict({"email": {**VALID, "attachments": {setting: value}}})
    return describe_validation_error(caught.value)


# ----------------------------------------------------------------------- the model


@pytest.mark.os_agnostic
@pytest.mark.parametrize("setting", LIST_SETTINGS)
def test_a_comma_separated_string_is_refused_not_dropped(setting: str) -> None:
    lines = _refusal(setting, COMMA_VALUE[setting])

    assert len(lines) == 1, lines
    assert lines[0].startswith(f"email.attachments.{setting}: "), lines
    assert "JSON array" in lines[0], lines


@pytest.mark.os_agnostic
@pytest.mark.parametrize("setting", LIST_SETTINGS)
def test_a_single_string_is_refused_too(setting: str) -> None:
    """One extension or directory is still a list of one; a bare string is not read as one."""
    lines = _refusal(setting, ".pdf" if "extensions" in setting else "/srv/outbox")

    assert [line.split(": ")[0] for line in lines] == [f"email.attachments.{setting}"]
    assert "JSON array" in lines[0], lines


@pytest.mark.os_agnostic
@pytest.mark.parametrize("setting", LIST_SETTINGS)
@pytest.mark.parametrize("value", [7, True, {"a": 1}], ids=["int", "bool", "dict"])
def test_a_value_of_another_type_is_refused(setting: str, value: object) -> None:
    lines = _refusal(setting, value)

    assert [line.split(": ")[0] for line in lines] == [f"email.attachments.{setting}"]
    assert "JSON array" in lines[0], lines


@pytest.mark.os_agnostic
@pytest.mark.parametrize("setting", LIST_SETTINGS)
@pytest.mark.parametrize("value", ["", "   ", []], ids=["empty", "whitespace", "empty-list"])
def test_an_empty_value_means_not_configured(setting: str, value: object) -> None:
    """Like an empty TOML array, an empty environment value leaves the library defaults."""
    config = load_email_config_from_dict({"email": {**VALID, "attachments": {setting: value}}})

    assert getattr(config, _field(setting)) == getattr(ConfMail(), _field(setting))


@pytest.mark.os_agnostic
def test_a_list_tuple_or_set_is_read_as_a_frozenset() -> None:
    config = EmailConfig.model_validate(
        {
            "attachment_allowed_extensions": [".pdf", ".txt"],
            "attachment_blocked_extensions": (".exe",),
            "attachment_allowed_directories": {"/srv/outbox"},
            "attachment_blocked_directories": frozenset({Path("/etc")}),
        }
    )

    assert config.attachment_allowed_extensions == frozenset({".pdf", ".txt"})
    assert config.attachment_blocked_extensions == frozenset({".exe"})
    assert config.attachment_allowed_directories == frozenset({Path("/srv/outbox")})
    assert config.attachment_blocked_directories == frozenset({Path("/etc")})


@pytest.mark.os_agnostic
def test_an_empty_blocked_set_needs_the_opt_in() -> None:
    """From Python an empty set is kept, not defaulted, so ConfMail asks for the opt-in that blocks nothing."""
    empty: dict[str, set[str]] = {"attachment_blocked_extensions": set(), "attachment_blocked_directories": set()}

    with pytest.raises(ValidationError):
        EmailConfig.model_validate(empty)
    config = EmailConfig.model_validate({**empty, "attachment_allow_empty_blocklists": True})

    assert config.attachment_blocked_extensions == frozenset()
    assert config.attachment_blocked_directories == frozenset()


@pytest.mark.os_agnostic
@pytest.mark.parametrize("field", ["smtphosts", "recipients"])
def test_a_tuple_of_hosts_or_recipients_is_kept(field: str) -> None:
    value = ("smtp.example.com:587",) if field == "smtphosts" else ("a@example.com",)

    assert getattr(EmailConfig.model_validate({field: value}), field) == list(value)


@pytest.mark.os_agnostic
@pytest.mark.parametrize("field", ["smtp_hosts", "recipients"])
@pytest.mark.parametrize("source", ["loader", "model"])
def test_a_host_or_recipient_list_set_to_none_means_not_configured(field: str, source: str) -> None:
    """A bare YAML key or an environment ``null`` clears the list instead of aborting the load."""
    if source == "loader":
        config = load_email_config_from_dict({"email": {field: None}})
    else:
        config = EmailConfig.model_validate({FILE_KEY_TO_FIELD.get(field, field): None})

    assert getattr(config, FILE_KEY_TO_FIELD.get(field, field)) == []


@pytest.mark.os_agnostic
@pytest.mark.parametrize("field", ["smtp_hosts", "recipients"])
def test_a_host_or_recipient_list_of_another_type_is_refused(field: str) -> None:
    with pytest.raises(ValidationError) as caught:
        load_email_config_from_dict({"email": {field: 587}})

    lines = describe_validation_error(caught.value)
    assert [line.split(": ")[0] for line in lines] == [f"email.{field}"]
    assert not lines[0].endswith(": unknown key"), lines


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


def _services(email: dict[str, Any], spy: EmailSpy) -> Callable[[], AppServices]:
    config = Config({"email": email}, {})

    def get_config(**_kwargs: Any) -> Config:
        return config

    return lambda: dataclasses.replace(
        build_testing(spy=spy), get_config=get_config, load_email_config_from_dict=load_email_config_from_dict
    )


@pytest.mark.os_agnostic
def test_send_email_exits_78_naming_the_setting(capsys: pytest.CaptureFixture[str]) -> None:
    email = {**VALID, "attachments": {"blocked_extensions": ".exe,.bat"}}
    spy = EmailSpy()

    exit_code = main(SEND_EMAIL, services_factory=_services(email, spy))

    err = capsys.readouterr().err
    assert exit_code == 78, err
    errors = [line for line in err.splitlines() if line.startswith("Error:")]
    assert len(errors) == 1, err
    assert errors[0].startswith("Error: Invalid configuration: email.attachments.blocked_extensions: "), err
    assert spy.sent_emails == []
