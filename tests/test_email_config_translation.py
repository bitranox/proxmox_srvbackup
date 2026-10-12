"""The merged [email] section becomes an EmailConfig: file keys kept, unknown keys refused.

lib_layered_config merges every layer into one mapping; load_email_config_from_dict reads its
[email] section. Six file keys differ from ConfMail's field names, values that mean "not
configured" are dropped so the library default applies, and a key that is not a file key is
refused, whatever layer it came from.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from btx_lib_mail import ConfMail
from pydantic import ValidationError

from proxmox_srvbackup.adapters.email.config import (
    EmailConfig,
    describe_validation_error,
    load_email_config_from_dict,
)


def _load(email: object) -> EmailConfig:
    return load_email_config_from_dict({"email": email})


def _problems(email: object) -> list[str]:
    with pytest.raises(ValidationError) as caught:
        _load(email)
    return describe_validation_error(caught.value)


@pytest.mark.os_agnostic
def test_the_six_renamed_file_keys_reach_their_fields() -> None:
    config = _load(
        {
            "smtp_hosts": ["smtp.example.com:587"],
            "use_starttls": False,
            "timeout": 12.5,
            "starttls_verify": False,
            "local_hostname": "mail.example.com",
            "delivery_deadline": 120,
        }
    )

    assert config.smtphosts == ["smtp.example.com:587"]
    assert config.smtp_use_starttls is False
    assert config.smtp_timeout == 12.5
    assert config.smtp_starttls_verify is False
    assert config.smtp_local_hostname == "mail.example.com"
    assert config.smtp_delivery_deadline == 120.0


@pytest.mark.os_agnostic
def test_attachment_keys_reach_their_prefixed_fields() -> None:
    config = _load({"attachments": {"max_size_bytes": 1024, "allow_symlinks": True, "allowed_extensions": [".PDF"]}})

    assert config.attachment_max_size_bytes == 1024
    assert config.attachment_allow_symlinks is True
    assert config.attachment_allowed_extensions == frozenset({".pdf"})


@pytest.mark.os_agnostic
@pytest.mark.parametrize("key", ["from_address", "smtp_username", "smtp_password", "local_hostname"])
@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_text_means_not_configured(key: str, blank: str) -> None:
    config = _load({key: blank})

    field = {"local_hostname": "smtp_local_hostname"}.get(key, key)
    assert getattr(config, field) is None


@pytest.mark.os_agnostic
@pytest.mark.parametrize("key", ["smtp_hosts", "recipients"])
@pytest.mark.parametrize("blank", ["", "  "], ids=["empty", "whitespace"])
def test_a_blank_list_string_means_an_empty_list(key: str, blank: str) -> None:
    config = _load({key: blank})

    assert getattr(config, {"smtp_hosts": "smtphosts"}.get(key, key)) == []


@pytest.mark.os_agnostic
@pytest.mark.parametrize("field", ["smtphosts", "recipients"])
@pytest.mark.parametrize("blank", ["", "  "], ids=["empty", "whitespace"])
def test_a_blank_list_string_from_python_means_an_empty_list(field: str, blank: str) -> None:
    """The loader drops blank text first, so only a model-level value reaches the validators."""
    assert getattr(EmailConfig.model_validate({field: blank}), field) == []


@pytest.mark.os_agnostic
def test_a_single_host_or_address_string_is_a_one_entry_list() -> None:
    config = _load({"smtp_hosts": "smtp.example.com:587", "recipients": "ops@example.com"})

    assert config.smtphosts == ["smtp.example.com:587"]
    assert config.recipients == ["ops@example.com"]


@pytest.mark.os_agnostic
def test_a_single_host_string_from_python_is_a_one_entry_list() -> None:
    assert EmailConfig.model_validate({"smtphosts": "smtp.example.com:587"}).smtphosts == ["smtp.example.com:587"]


@pytest.mark.os_agnostic
def test_empty_attachment_lists_mean_the_library_defaults() -> None:
    lists: dict[str, list[str]] = {
        "allowed_extensions": [],
        "blocked_extensions": [],
        "allowed_directories": [],
        "blocked_directories": [],
    }
    config = _load({"attachments": lists})
    defaults = ConfMail()

    assert config.attachment_allowed_extensions is None
    assert config.attachment_allowed_directories is None
    assert config.attachment_blocked_extensions == defaults.attachment_blocked_extensions
    assert config.attachment_blocked_directories == defaults.attachment_blocked_directories


@pytest.mark.os_agnostic
def test_a_size_limit_of_zero_means_no_limit() -> None:
    assert _load({"attachments": {"max_size_bytes": 0}}).attachment_max_size_bytes is None


@pytest.mark.os_agnostic
@pytest.mark.parametrize(
    ("email", "field"),
    [
        ({"recipient_max_count": 0}, "recipient_max_count"),
        ({"delivery_deadline": 0}, "smtp_delivery_deadline"),
        ({"delivery_deadline": 0.0}, "smtp_delivery_deadline"),
        ({"attachments": {"max_count": 0}}, "attachment_max_count"),
    ],
    ids=["recipient_max_count", "delivery_deadline", "delivery_deadline_float", "attachments.max_count"],
)
def test_every_other_limit_of_zero_means_no_limit(email: dict[str, Any], field: str) -> None:
    assert getattr(_load(email), field) is None


@pytest.mark.os_agnostic
def test_the_limits_reach_their_fields() -> None:
    config = _load({"recipient_max_count": 5, "delivery_deadline": 120, "attachments": {"max_count": 3}})

    assert (config.recipient_max_count, config.smtp_delivery_deadline, config.attachment_max_count) == (5, 120.0, 3)


@pytest.mark.os_agnostic
def test_a_negative_deadline_is_named_by_its_file_key() -> None:
    (line,) = _problems({"delivery_deadline": -1})

    assert line.startswith("email.delivery_deadline: ")
    assert "smtp_delivery_deadline" not in line
    assert "unknown key" not in line


@pytest.mark.os_agnostic
@pytest.mark.parametrize(
    ("email", "line"),
    [
        ({"smtp_host": "smtp.example.com"}, "email.smtp_host: unknown key"),
        ({"smtp_timeout": 5}, "email.smtp_timeout: unknown key"),
        ({"attachment_max_size_bytes": 5}, "email.attachment_max_size_bytes: unknown key"),
        ({"attachments": {"max_size": 5}}, "email.attachments.max_size: unknown key"),
        ({"attachments": {"allow_empty_blocklists": True}}, "email.attachments.allow_empty_blocklists: unknown key"),
    ],
    ids=["typo", "library-name", "flattened-name", "attachment-typo", "not-exposed"],
)
def test_a_key_that_is_not_a_file_key_is_refused(email: dict[str, Any], line: str) -> None:
    assert _problems(email) == [line]


@pytest.mark.os_agnostic
def test_an_attachments_value_that_is_not_a_table_is_refused() -> None:
    assert _problems({"attachments": "none"}) == ["email.attachments: Input should be a valid dictionary"]


@pytest.mark.os_agnostic
def test_every_unknown_key_is_named_in_one_report() -> None:
    assert _problems({"smtp_host": "h", "attachments": {"maxsize": 1}}) == [
        "email.smtp_host: unknown key",
        "email.attachments.maxsize: unknown key",
    ]


@pytest.mark.os_agnostic
@pytest.mark.parametrize(
    ("email", "line"),
    [
        ({"timeout": -5}, "email.timeout: timeout must be positive, got -5.0"),
        (
            {"attachments": {"max_size_bytes": -1}},
            "email.attachments.max_size_bytes: attachments.max_size_bytes must be positive, got -1",
        ),
    ],
    ids=["timeout", "attachment"],
)
def test_a_refused_value_is_named_by_its_file_key_in_the_location_and_the_reason(
    email: dict[str, Any], line: str
) -> None:
    assert _problems(email) == [line]


@pytest.mark.os_agnostic
def test_a_comma_separated_extension_string_is_refused_not_ignored() -> None:
    problems = _problems({"attachments": {"allowed_extensions": ".pdf,.txt"}})

    assert len(problems) == 1
    assert problems[0].startswith("email.attachments.allowed_extensions: ")


@pytest.mark.os_agnostic
def test_every_email_config_field_but_one_is_reachable_from_exactly_one_file_key() -> None:
    """Pins the key lists against the model: a field ConfMail adds later must be decided here."""
    from proxmox_srvbackup.adapters.email import config as module

    reachable = [module.FILE_KEY_TO_FIELD.get(key, key) for key in module.SECTION_KEYS - {"attachments"}]
    reachable += [f"attachment_{key}" for key in module.ATTACHMENT_KEYS]

    assert sorted(reachable) == sorted(set(EmailConfig.model_fields) - {"attachment_allow_empty_blocklists"})


@pytest.mark.os_agnostic
def test_the_model_refuses_unknown_python_names_too() -> None:
    with pytest.raises(ValidationError):
        EmailConfig.model_validate({"smtp_hosts": ["h"]})


@pytest.mark.os_agnostic
def test_a_directory_list_becomes_paths() -> None:
    config = _load({"attachments": {"allowed_directories": ["/srv/exports"]}})

    assert config.attachment_allowed_directories == frozenset({Path("/srv/exports")})


@pytest.mark.os_agnostic
@pytest.mark.parametrize(
    "host", ["smtp.example.com:99999", "smtp.example.com:abc", "[::1"], ids=["port-range", "port-text", "bracket"]
)
def test_a_malformed_host_is_refused_at_load(host: str) -> None:
    """A port or bracket typo surfaces when the configuration loads, not at the first delivery."""
    problems = _problems({"smtp_hosts": [host]})

    assert len(problems) == 1, problems
    assert problems[0].startswith("email.smtp_hosts: "), problems
    assert "Value error" not in problems[0], problems


@pytest.mark.os_agnostic
@pytest.mark.parametrize(
    "host",
    ["smtp.example.com:99999", "smtp.example.com:abc", "[::1", "smtp.example.com:+25", "a..example.com", "[zz]"],
    ids=["port-range", "port-text", "bracket", "port-sign", "empty-label", "bracket-not-ip"],
)
def test_conf_mail_itself_refuses_a_malformed_host(host: str) -> None:
    """EmailConfig has no host check of its own: ConfMail runs validate_smtp_host on every entry.

    If a btx_lib_mail release stops doing so, this fails, and the check belongs back in EmailConfig.
    """
    with pytest.raises(ValidationError):
        ConfMail(smtphosts=[host])


@pytest.mark.os_agnostic
def test_a_host_list_of_the_wrong_type_reads_as_the_file_key_without_a_prefix() -> None:
    """btx_lib_mail drops ctx for a credential field, so pydantic's prefix is still on the message."""
    assert _problems({"smtp_hosts": 587}) == [
        "email.smtp_hosts: smtp_hosts must be a string, list of strings, or tuple of strings"
    ]


@pytest.mark.os_agnostic
def test_an_all_digit_user_name_from_the_environment_is_read_as_text() -> None:
    """lib_layered_config reads an all-digit environment value as an int."""
    assert _load({"smtp_username": 4711}).smtp_username == "4711"


@pytest.mark.os_agnostic
@pytest.mark.parametrize(
    "setting", ["allowed_extensions", "blocked_extensions", "allowed_directories", "blocked_directories"]
)
@pytest.mark.parametrize("entry", ["", "   "], ids=["empty", "whitespace"])
def test_a_blank_entry_in_an_attachment_list_is_refused(setting: str, entry: str) -> None:
    """A blank directory became Path('.'), which REPLACED the OS defaults and blocked nothing."""
    problems = _problems({"attachments": {setting: ["/srv/x" if "directories" in setting else ".pdf", entry]}})

    assert problems == [f"email.attachments.{setting}: an entry is blank; remove it"]


@pytest.mark.os_agnostic
@pytest.mark.parametrize("field", ["smtp_username", "smtp_password"])
@pytest.mark.parametrize("blank", ["", "   "], ids=["empty", "whitespace"])
def test_a_blank_credential_from_python_means_no_login(field: str, blank: str) -> None:
    config = EmailConfig.model_validate({"smtp_username": "u", "smtp_password": "p", field: blank})

    assert getattr(config, field) is None
    assert config.resolved_credentials() is None


@pytest.mark.os_agnostic
def test_python_callers_keep_the_lenient_reading_of_text_fields() -> None:
    """Blank sender, a lone recipient string and an all-digit user name, as before ConfMail."""
    config = EmailConfig.model_validate({"from_address": "  ", "recipients": "ops@example.com", "smtp_username": 4711})

    assert config.from_address is None
    assert config.recipients == ["ops@example.com"]
    assert config.smtp_username == "4711"


@pytest.mark.os_agnostic
def test_an_unknown_key_with_control_characters_is_shown_escaped() -> None:
    (line,) = _problems({"smtp\x1b[31mhost\rX": "h"})

    assert line == "email.smtp\\x1b[31mhost\\rX: unknown key"
    assert line.isprintable()


@pytest.mark.os_agnostic
def test_a_size_limit_of_zero_written_as_a_float_means_no_limit() -> None:
    assert _load({"attachments": {"max_size_bytes": 0.0}}).attachment_max_size_bytes is None
