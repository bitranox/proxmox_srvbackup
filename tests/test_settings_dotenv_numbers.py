"""A digit-only ``.env`` value reaches the text settings as the digits the operator wrote.

lib_layered_config reads an unquoted ``.env`` or environment value that spells a number
losslessly as an int (``EMAIL__SMTP_PASSWORD=123456`` arrives as ``123456``). These tests load a
real ``.env`` through the real loader, assert the library really hands over an int (the premise;
if upstream stops doing so the test says so instead of passing vacuously), then parse it on the
production path.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest
from pydantic import ValidationError

from proxmox_srvbackup.adapters.cli.commands.backup import (
    _servers_from_config,  # pyright: ignore[reportPrivateUsage]
)
from proxmox_srvbackup.adapters.config.loader import get_config
from proxmox_srvbackup.adapters.email.config import load_email_config_from_dict
from proxmox_srvbackup.adapters.logging.setup import LoggingConfigModel

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from lib_layered_config import Config


def _load(tmp_path: Path, text: str) -> Config:
    dotenv = tmp_path / ".env"
    dotenv.write_text(text, encoding="utf-8")
    return get_config(dotenv_path=str(dotenv), start_dir=str(tmp_path))


def _section(config: Config, name: str) -> dict[str, object]:
    return dict(cast("Mapping[str, object]", config.as_dict()[name]))


@pytest.mark.os_agnostic
def test_digit_only_email_credentials_stay_text(tmp_path: Path, clear_config_cache: None) -> None:
    config = _load(tmp_path, "EMAIL__SMTP_PASSWORD=123456\nEMAIL__SMTP_USERNAME=4711\n")
    section = _section(config, "email")
    assert isinstance(section["smtp_password"], int)
    assert isinstance(section["smtp_username"], int)

    email = load_email_config_from_dict(config.as_dict())

    assert email.smtp_password is not None
    assert email.smtp_password.get_secret_value() == "123456"
    assert email.smtp_username == "4711"


@pytest.mark.os_agnostic
def test_digit_only_logging_text_settings_stay_text(tmp_path: Path, clear_config_cache: None) -> None:
    config = _load(tmp_path, "LIB_LOG_RICH__SERVICE=2770\nLIB_LOG_RICH__ENVIRONMENT=2026\n")
    section = _section(config, "lib_log_rich")
    assert isinstance(section["service"], int)
    assert isinstance(section["environment"], int)

    model = LoggingConfigModel.model_validate(section)

    assert (model.service, model.environment) == ("2770", "2026")


@pytest.mark.os_agnostic
def test_digit_only_server_text_settings_stay_text(tmp_path: Path, clear_config_cache: None) -> None:
    config = _load(tmp_path, "BACKUP__SERVERS__PX01__HOSTNAME=10\nBACKUP__SERVERS__PX01__ZFS_POOL=2026\n")
    servers = cast("Mapping[str, Mapping[str, object]]", _section(config, "backup")["servers"])
    assert isinstance(servers["px01"]["hostname"], int)
    assert isinstance(servers["px01"]["zfs_pool"], int)

    (server,) = _servers_from_config(config.as_dict())

    assert (server.hostname, server.zfs_pool) == ("10", "2026")


@pytest.mark.os_agnostic
def test_a_non_text_value_is_still_refused() -> None:
    with pytest.raises(ValidationError):
        LoggingConfigModel.model_validate({"service": ["a"]})
