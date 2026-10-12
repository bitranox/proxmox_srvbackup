"""The EmailConfig field table in the module reference matches the model.

A derived repo reads ``docs/systemdesign/module_reference.md`` to learn what to pass to
``EmailConfig``; a type there that no longer matches the model (``smtp_password`` documented
as ``str | None`` after it became a ``SecretStr``) sends it to write code that fails strict
type checking.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import get_args

import pytest

from proxmox_srvbackup.adapters.email.config import EmailConfig

_MODULE_REFERENCE = Path(__file__).parent.parent / "docs" / "systemdesign" / "module_reference.md"
_ROW = re.compile(r"\|\s*`(\w+)`\s*\|\s*`([^`]+)`\s*\|")


def _documented_types() -> dict[str, str]:
    """Each ``| `field` | `type` |`` row of the module reference, the type with ``\\|`` unescaped."""
    rows: dict[str, str] = {}
    for line in _MODULE_REFERENCE.read_text(encoding="utf-8").splitlines():
        match = _ROW.match(line)
        if match:
            rows[match.group(1)] = match.group(2).replace("\\|", "|")
    return rows


def _spelled(annotation: object) -> str:
    """The annotation as the table spells it: bare class names, no module paths."""
    # get_args first: on Python 3.10 a parametrised builtin such as list[str] passes
    # isinstance(..., type), so its __name__ would spell it as plain "list".
    text = annotation.__name__ if isinstance(annotation, type) and not get_args(annotation) else str(annotation)
    return re.sub(r"\b(?:[a-z_]\w*\.)+(\w+)", r"\1", text)


@pytest.mark.os_agnostic
def test_every_email_config_field_is_documented_with_its_type() -> None:
    documented = _documented_types()

    mismatched = {
        name: (documented.get(name), _spelled(field.annotation))
        for name, field in EmailConfig.model_fields.items()
        if documented.get(name) != _spelled(field.annotation)
    }

    assert mismatched == {}, "field: (documented, actual)"
