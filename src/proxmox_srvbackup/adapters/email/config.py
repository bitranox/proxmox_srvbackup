"""Email configuration: the merged ``[email]`` section as a btx_lib_mail ``ConfMail``.

lib_layered_config is the only reader of configuration. It merges every layer (the shipped
defaults, the app, host and user files, ``.env``, the environment and ``--set``) into one
mapping, and :func:`load_email_config_from_dict` turns that mapping's ``[email]`` section into
:class:`EmailConfig`. Operators keep writing the file keys they always wrote; six of them
differ from the field names code reads (``FILE_KEY_TO_FIELD``). A key that is not a file key
is refused, so a typo cannot leave a setting silently at its default.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, cast

from btx_lib_mail import ConfMail, validate_email_address
from pydantic import ConfigDict, Field, SecretStr, ValidationError, field_validator

if TYPE_CHECKING:
    from pydantic_core import ErrorDetails, InitErrorDetails

#: The configuration section EmailConfig is read from.
_SECTION = "email"
#: The nested table that holds the attachment settings.
_ATTACHMENTS = "attachments"
#: The field-name prefix that stands for that table.
_ATTACHMENT_PREFIX = "attachment_"

#: File key -> EmailConfig field, for the keys whose names differ.
FILE_KEY_TO_FIELD: dict[str, str] = {
    "smtp_hosts": "smtphosts",
    "use_starttls": "smtp_use_starttls",
    "timeout": "smtp_timeout",
    "starttls_verify": "smtp_starttls_verify",
    "local_hostname": "smtp_local_hostname",
    "delivery_deadline": "smtp_delivery_deadline",
}
_FIELD_TO_FILE_KEY: dict[str, str] = {field: key for key, field in FILE_KEY_TO_FIELD.items()}

#: Every key ``[email]`` accepts.
SECTION_KEYS = frozenset(
    {
        *FILE_KEY_TO_FIELD,
        "from_address",
        "recipients",
        "smtp_username",
        "smtp_password",
        "raise_on_missing_attachments",
        "raise_on_invalid_recipient",
        "recipient_max_count",
        _ATTACHMENTS,
    }
)
#: Every key ``[email.attachments]`` accepts; each names the field ``attachment_<key>``.
#: ``allow_empty_blocklists`` is deliberately absent: an empty blocked list means the defaults.
ATTACHMENT_KEYS = frozenset(
    {
        "allowed_extensions",
        "blocked_extensions",
        "allowed_directories",
        "blocked_directories",
        "max_size_bytes",
        "max_count",
        "allow_symlinks",
        "raise_on_security_violation",
    }
)
#: Keys whose blank text means "not configured": the shipped defaults write "" for them, and the
#: model would otherwise keep it (an empty host, a login attempt with an empty password).
_BLANK_TEXT_MEANS_UNSET = frozenset(
    {"smtp_hosts", "recipients", "from_address", "smtp_username", "smtp_password", "local_hostname"}
)
#: Attachment lists whose empty value means "the library's defaults". For ConfMail an empty
#: allowed list allows nothing and an empty blocked list blocks nothing, so passing [] through
#: would refuse every attachment or switch the protection off.
_EMPTY_LIST_MEANS_DEFAULT = frozenset(
    {"allowed_extensions", "blocked_extensions", "allowed_directories", "blocked_directories"}
)
#: Limits whose 0 means "no limit". ConfMail refuses 0 and lifts a limit with None, which a
#: TOML file or an environment variable cannot write.
_ZERO_MEANS_NO_LIMIT = frozenset({"max_size_bytes", "max_count", "recipient_max_count", "delivery_deadline"})
#: The refusal of a blank entry in an attachment list.
_BLANK_ENTRY = ValueError("an entry is blank; remove it")
#: The form an attachment list must take, named by the refusal of any other form. A
#: comma-separated environment value stays one string; read as "not configured" it would swap
#: the configured list for the library's defaults without a word, so it is refused instead.
_LIST_FORM = 'a list: a TOML array, or in an environment variable a JSON array such as [".pdf", ".txt"]'
#: Lists the environment can only deliver as one string when they hold one entry.
_ONE_OR_MANY = frozenset({"smtp_hosts", "recipients"})
#: What pydantic puts in front of the message of a ValueError a validator raised.
_VALUE_ERROR_PREFIX = "Value error, "
#: A field name inside a library message, rewritten so the reader sees the key they wrote.
_FIELD_NAME_IN_TEXT = re.compile(
    r"\b(?:" + "|".join(map(re.escape, _FIELD_TO_FILE_KEY)) + "|" + _ATTACHMENT_PREFIX + r"\w+)\b"
)


class EmailConfig(ConfMail):
    """btx_lib_mail's ``ConfMail`` plus the sender and the default recipients.

    Inherits the ``SecretStr`` password, the host, timeout and EHLO-name validation, the
    attachment policy and validation errors that never show the password or a host. Frozen, and a name
    that is not a field is refused rather than ignored.

    Example:
        >>> config = EmailConfig(smtphosts=["smtp.example.com:587"], from_address="noreply@example.com")
        >>> config.smtphosts
        ['smtp.example.com:587']
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    from_address: str | None = None
    recipients: list[str] = Field(default_factory=list)

    @field_validator("smtp_username", "smtp_password", mode="before")
    @classmethod
    def _blank_credential_is_none(cls, value: object) -> object:
        """A blank user name or password means no login; an all-digit user name is its digits.

        ConfMail keeps blank text, and a blank user name next to a password is truthy enough to
        attempt a login. The environment layer reads an all-digit value as an ``int``; ConfMail
        reads the password as its digits, so the user name gets the same treatment.

        Examples:
            >>> EmailConfig._blank_credential_is_none("   ") is None
            True
            >>> EmailConfig._blank_credential_is_none(4711)
            '4711'
        """
        text = value.get_secret_value() if isinstance(value, SecretStr) else value
        if isinstance(text, str) and not text.strip():
            return None
        if type(value) is int:
            return str(value)
        return value

    @field_validator("from_address", mode="before")
    @classmethod
    def _blank_sender_is_none(cls, value: object) -> object:
        return None if isinstance(value, str) and not value.strip() else value

    @field_validator("recipients", mode="before")
    @classmethod
    def _one_recipient_is_a_list(cls, value: object) -> object:
        # The same reading ConfMail gives smtphosts: one address is a one-entry list, and None
        # (a bare YAML key, an environment null) means no default recipients.
        if value is None:
            return []
        if isinstance(value, str):
            return [value] if value.strip() else []
        return value

    @field_validator("from_address")
    @classmethod
    def _check_from_address(cls, value: str | None) -> str | None:
        if value is not None:
            validate_email_address(value)
        return value

    @field_validator("recipients")
    @classmethod
    def _check_recipients(cls, value: list[str]) -> list[str]:
        for recipient in value:
            validate_email_address(recipient)
        return value


def load_email_config_from_dict(config_dict: Mapping[str, Any]) -> EmailConfig:
    """Turn the ``[email]`` section of the merged configuration into an :class:`EmailConfig`.

    Args:
        config_dict: The mapping lib_layered_config produced (``Config.as_dict()``).

    Returns:
        The validated configuration; a missing section gives the defaults.

    Raises:
        ValidationError: A key that is not a file key (every one is named, before any value is
            checked), or a value the model refuses.

    Example:
        >>> load_email_config_from_dict({"email": {"smtp_hosts": ["smtp.example.com:587"]}}).smtphosts
        ['smtp.example.com:587']
        >>> load_email_config_from_dict({"email": {"timeout": 10}}).smtp_timeout
        10.0
    """
    section: object = config_dict.get(_SECTION, {})
    if not isinstance(section, Mapping):
        return EmailConfig.model_validate(section)
    return EmailConfig.model_validate(_translate(cast("Mapping[str, Any]", section)))


def _translate(section: Mapping[str, Any]) -> dict[str, Any]:
    """Map file keys onto field names and drop the values that mean "not configured"."""
    refused = _refused_keys(section)
    if refused:
        raise ValidationError.from_exception_data(EmailConfig.__name__, refused, hide_input=True)
    fields: dict[str, Any] = {}
    for key, value in section.items():
        if key == _ATTACHMENTS:
            fields.update(_attachment_fields(cast("Mapping[str, Any]", value)))
        elif not _means_unset(key, value):
            fields[FILE_KEY_TO_FIELD.get(key, key)] = _field_value(key, value)
    return fields


def _attachment_fields(table: Mapping[str, Any]) -> dict[str, Any]:
    return {
        f"{_ATTACHMENT_PREFIX}{key}": _field_value(key, value)
        for key, value in table.items()
        if not _means_unset(key, value)
    }


def _refused_keys(section: Mapping[str, Any]) -> list[InitErrorDetails]:
    """Every key the section does not accept, and an ``attachments`` value that is not a table."""
    refused = [_problem("extra_forbidden", (key,)) for key in section if key not in SECTION_KEYS]
    attachments: object = section.get(_ATTACHMENTS, {})
    if not isinstance(attachments, Mapping):
        return [*refused, _problem("dict_type", (_ATTACHMENTS,))]
    table = cast("Mapping[str, Any]", attachments)
    unknown_in_table = (key for key in table if key not in ATTACHMENT_KEYS)
    wrong_form = (key for key in _EMPTY_LIST_MEANS_DEFAULT if key in table and not _is_list_form(table[key]))
    blank_entry = (key for key in _EMPTY_LIST_MEANS_DEFAULT if key in table and _has_blank_entry(table[key]))
    return [
        *refused,
        *(_problem("extra_forbidden", (_ATTACHMENTS, key)) for key in unknown_in_table),
        *(_problem("value_error", (_ATTACHMENTS, key), _wrong_list_form(table[key])) for key in wrong_form),
        *(_problem("value_error", (_ATTACHMENTS, key), _BLANK_ENTRY) for key in blank_entry),
    ]


def _is_list_form(value: object) -> bool:
    """A list, tuple or set, None, or blank text (an environment variable set to nothing)."""
    if value is None or isinstance(value, (list, tuple, set, frozenset)):
        return True
    return isinstance(value, str) and not value.strip()


def _has_blank_entry(value: object) -> bool:
    # A blank directory becomes Path("."), which replaces the OS defaults and blocks nothing; a
    # blank extension is dropped, which can leave an empty blocked list.
    if not isinstance(value, (list, tuple)):
        return False
    items = cast("list[object] | tuple[object, ...]", value)
    return any(isinstance(item, str) and not item.strip() for item in items)


def _wrong_list_form(value: object) -> ValueError:
    return ValueError(f"expected {_LIST_FORM}; got {type(value).__name__}")


def _problem(kind: str, loc: tuple[str, ...], error: ValueError | None = None) -> InitErrorDetails:
    # No input: the value under an unknown key can be a password typed under a wrong name.
    if error is None:
        return {"type": kind, "loc": loc, "input": None}
    return {"type": kind, "loc": loc, "input": None, "ctx": {"error": error}}


def _means_unset(key: str, value: object) -> bool:
    if key in _EMPTY_LIST_MEANS_DEFAULT:
        # Not an empty set: that is a deliberate choice from Python code, and ConfMail judges it.
        return value is None or value in ([], ()) or (isinstance(value, str) and not value.strip())
    if isinstance(value, str) and key in _BLANK_TEXT_MEANS_UNSET:
        return not value.strip()
    return False


def _field_value(key: str, value: object) -> object:
    """A lone host or address becomes a one-entry list; a limit of 0 means no limit."""
    if key in _ONE_OR_MANY and isinstance(value, str):
        return [value]
    if key in _ZERO_MEANS_NO_LIMIT and type(value) in (int, float) and value == 0:
        return None
    return value


def _file_key_for(field: str) -> str:
    """The key a reader writes for a field.

    Examples:
        >>> _file_key_for("smtp_timeout")
        'timeout'
        >>> _file_key_for("attachment_max_size_bytes")
        'attachments.max_size_bytes'
        >>> _file_key_for("from_address")
        'from_address'
    """
    if field.startswith(_ATTACHMENT_PREFIX):
        return f"{_ATTACHMENTS}.{field.removeprefix(_ATTACHMENT_PREFIX)}"
    return _FIELD_TO_FILE_KEY.get(field, field)


def _configuration_key(loc: tuple[int | str, ...]) -> str:
    """Spell a validation error's location as the dotted key a user writes.

    Examples:
        >>> _configuration_key(("smtp_timeout",))
        'email.timeout'
        >>> _configuration_key(("attachments", "max_size"))
        'email.attachments.max_size'
        >>> _configuration_key(())
        'email'
    """
    parts = [str(part) for part in loc]
    if parts:
        parts[0] = _file_key_for(parts[0])
    return ".".join((_SECTION, *parts))


def _line(item: ErrorDetails) -> str:
    if item["type"] == "extra_forbidden":
        # The location is the key as written, not a field: mapping it would turn an unknown
        # ``smtp_timeout`` into ``email.timeout``, a key that exists and is not the problem.
        return f"{'.'.join((_SECTION, *map(_escaped, item['loc'])))}: unknown key"
    return f"{_configuration_key(item['loc'])}: {_reason(item)}"


def _escaped(part: int | str) -> str:
    r"""A key as written, with control characters shown as escapes rather than acted on.

    Examples:
        >>> _escaped("smtp\x1b[31mhost")
        'smtp\\x1b[31mhost'
    """
    return "".join(char if char.isprintable() else repr(char)[1:-1] for char in str(part))


def _reason(item: ErrorDetails) -> str:
    # pydantic prefixes a validator's ValueError with "Value error, "; the exception it carries
    # holds the message as written. For a credential field btx_lib_mail drops that exception
    # (it could carry the value), so the prefix comes off the message itself. The library
    # names its own fields; show the file key.
    raised = item.get("ctx", {}).get("error")
    if isinstance(raised, ValueError):
        text = str(raised)
    elif item["type"] == "value_error":
        text = item["msg"].removeprefix(_VALUE_ERROR_PREFIX)
    else:
        text = item["msg"]
    return _FIELD_NAME_IN_TEXT.sub(lambda match: _file_key_for(match.group(0)), text)


def describe_validation_error(error: ValidationError) -> list[str]:
    """Render an EmailConfig validation error as one ``<key>: <reason>`` line per problem.

    The refused input is never part of a line: it can be the SMTP password.

    Args:
        error: The error loading or overriding ``EmailConfig`` raised.

    Returns:
        One line per problem; the key is ``email`` alone for a problem with the whole section.

    Example:
        >>> try:
        ...     load_email_config_from_dict({"email": {"timeout": -5}})
        ... except ValidationError as exc:
        ...     describe_validation_error(exc)
        ['email.timeout: timeout must be positive, got -5.0']
        >>> try:
        ...     load_email_config_from_dict({"email": {"smtp_host": "smtp.example.com"}})
        ... except ValidationError as exc:
        ...     describe_validation_error(exc)
        ['email.smtp_host: unknown key']
    """
    return [_line(item).replace("\n", " ") for item in error.errors(include_url=False, include_input=False)]


__all__ = [
    "ATTACHMENT_KEYS",
    "FILE_KEY_TO_FIELD",
    "SECTION_KEYS",
    "EmailConfig",
    "describe_validation_error",
    "load_email_config_from_dict",
]
