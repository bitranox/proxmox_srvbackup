"""Parse and apply ``--set SECTION.KEY=VALUE`` CLI overrides to Config."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

import orjson
from lib_layered_config import Config

if TYPE_CHECKING:
    from lib_layered_config.domain.config import SourceInfo

CLI_LAYER = "cli"
"""Provenance layer recorded for a value that came from ``--set``.

It is not one of the library's file layers because it names no file: the
value was typed on the command line and there is nothing to open.
"""

CoercedValue = str | int | float | bool | None | list[object] | dict[str, object]
"""Union of types that :func:`coerce_value` can produce."""


@dataclass(frozen=True, slots=True)
class ConfigOverride:
    """A single parsed configuration override."""

    section: str
    key_path: tuple[str, ...]
    value: CoercedValue


def parse_override(raw: str) -> ConfigOverride:
    """Split a ``SECTION.KEY[.SUBKEY...]=VALUE`` string into a ConfigOverride.

    The first dot separates the top-level section from the key path.
    The first ``=`` separates the full dotted path from the value.
    Values are coerced via :func:`coerce_value`.

    Args:
        raw: Raw override string (e.g., ``lib_log_rich.console_level=DEBUG``).

    Returns:
        Parsed ConfigOverride with section, key_path tuple, and coerced value.

    Raises:
        ValueError: If the string lacks ``=``, has no dot in the key, or has
            empty section/key components.

    Examples:
        >>> override = parse_override("lib_log_rich.console_level=DEBUG")
        >>> override.section
        'lib_log_rich'
        >>> override.key_path
        ('console_level',)
        >>> override.value
        'DEBUG'

        >>> override = parse_override("lib_log_rich.payload_limits.max_chars=8192")
        >>> override.key_path
        ('payload_limits', 'max_chars')
        >>> override.value
        8192
    """
    if "=" not in raw:
        raise ValueError(f"Invalid override {raw!r}: must contain '='")

    path_part, value_str = raw.split("=", maxsplit=1)

    if "." not in path_part:
        raise ValueError(f"Invalid override {raw!r}: key must contain at least one dot (SECTION.KEY)")

    parts = path_part.split(".")
    section = parts[0]
    key_parts = tuple(parts[1:])

    if not section:
        raise ValueError(f"Invalid override {raw!r}: section name is empty")
    if not all(key_parts):
        raise ValueError(f"Invalid override {raw!r}: key path contains empty component")

    return ConfigOverride(
        section=section,
        key_path=key_parts,
        value=coerce_value(value_str),
    )


def coerce_value(raw: str) -> CoercedValue:
    """Coerce a raw string value using JSON parsing with string fallback.

    Attempts ``orjson.loads`` first (handling booleans, numbers, null, arrays,
    objects). Falls back to the raw string if JSON parsing fails.

    Args:
        raw: Raw value string from CLI.

    Returns:
        Parsed Python value (bool, int, float, None, list, dict) or the
        original string.

    Examples:
        >>> coerce_value("true")
        True
        >>> coerce_value("42")
        42
        >>> coerce_value("3.14")
        3.14
        >>> coerce_value("null")
        >>> coerce_value('["a","b"]')
        ['a', 'b']
        >>> coerce_value("DEBUG")
        'DEBUG'
        >>> coerce_value("")
        ''
    """
    if raw == "":
        return ""
    try:
        return orjson.loads(raw)
    except (orjson.JSONDecodeError, ValueError):
        return raw


def _nest_override(target: dict[str, dict[str, object]], override: ConfigOverride) -> None:
    """Build a nested override dict from a parsed ConfigOverride.

    Creates intermediate dicts as needed. The resulting dict structure
    is passed to ``Config.with_overrides()`` for merge.

    Args:
        target: Mutable override dictionary being built.
        override: Parsed override containing section, key_path, and value.

    Examples:
        >>> d: dict[str, dict[str, object]] = {}
        >>> _nest_override(d, ConfigOverride(section="s", key_path=("a",), value=2))
        >>> d["s"]["a"]
        2
        >>> d2: dict[str, dict[str, object]] = {}
        >>> _nest_override(d2, ConfigOverride(section="new", key_path=("x", "y"), value=3))
        >>> d2["new"]["x"]["y"]
        3
    """
    node: dict[str, object] = target.setdefault(override.section, {})
    for part in override.key_path[:-1]:
        # Always a table: nest_overrides refuses a key given both a value and keys under it
        # before nesting, so no override's value ever sits where another needs a table.
        node = cast("dict[str, object]", node.setdefault(part, {}))
    node[override.key_path[-1]] = override.value


def _refuse_conflicts(dotted_keys: list[str]) -> None:
    """Refuse a key that one override gives a value and another gives keys under.

    Either order is a contradiction on the command line: nesting ``a.b.c`` under the value
    of ``a.b`` fails, and ``a.b=1`` after ``a.b.c=2`` would silently drop the earlier one.

    Raises:
        ValueError: Naming the key and the override that puts a key under it.

    Examples:
        >>> _refuse_conflicts(["a.b", "a.bc", "a.b"])
        >>> _refuse_conflicts(["a.b.c", "a.b"])
        Traceback (most recent call last):
        ...
        ValueError: conflicting --set overrides: a.b is given a value and a.b.c puts a key under it
    """
    for key in dotted_keys:
        nested = next((other for other in dotted_keys if other.startswith(f"{key}.")), None)
        if nested is not None:
            raise ValueError(f"conflicting --set overrides: {key} is given a value and {nested} puts a key under it")


def nest_overrides(raw_overrides: tuple[str, ...]) -> tuple[dict[str, dict[str, object]], frozenset[str]]:
    """Parse ``--set`` values into the nested mapping they override, checking them together.

    Args:
        raw_overrides: Tuple of ``SECTION.KEY=VALUE`` strings from ``--set``.

    Returns:
        The nested override mapping and the dotted keys it sets. For one key given twice,
        the last value wins.

    Raises:
        ValueError: An override is malformed, or two of them conflict (one gives a key a
            value, another puts a key under it).

    Example:
        >>> tree, keys = nest_overrides(("a.b=1", "a.c.d=x"))
        >>> tree, sorted(keys)
        ({'a': {'b': 1, 'c': {'d': 'x'}}}, ['a.b', 'a.c.d'])
    """
    parsed = [parse_override(raw) for raw in raw_overrides]
    dotted_keys = [".".join((override.section, *override.key_path)) for override in parsed]
    _refuse_conflicts(dotted_keys)
    overrides: dict[str, dict[str, object]] = {}
    for override in parsed:
        _nest_override(overrides, override)
    return overrides, frozenset(dotted_keys)


def _dotted_keys(data: Mapping[str, object], prefix: str = "") -> Iterator[str]:
    """Yield every leaf key of a nested mapping in dotted form.

    Args:
        data: The nested mapping to walk.
        prefix: Dotted path accumulated by the caller, ending in a dot.

    Yields:
        One dotted path per leaf value.

    Example:
        >>> sorted(_dotted_keys({"a": {"b": 1, "c": {"d": 2}}}))
        ['a.b', 'a.c.d']
    """
    for key, value in data.items():
        path = f"{prefix}{key}"
        if isinstance(value, Mapping):
            yield from _dotted_keys(cast("Mapping[str, object]", value), f"{path}.")
        else:
            yield path


def _provenance_naming_the_cli(
    config: Config, merged_as_dict: Mapping[str, object], overridden: frozenset[str]
) -> dict[str, SourceInfo]:
    """Copy a Config's provenance, relabelling the keys an override replaced.

    Args:
        config: The Config the values came from, holding the original map.
        merged_as_dict: The merged Config's own mapping, walked for the full
            key set. Passed in already computed, because the caller needs the
            same mapping to build the merged ``Config``.
        overridden: Dotted keys that ``--set`` supplied.

    Returns:
        A provenance map naming the CLI for overridden keys and the original
        source for every other one.
    """
    provenance: dict[str, SourceInfo] = {}
    for dotted in _dotted_keys(merged_as_dict):
        if dotted in overridden:
            provenance[dotted] = {"layer": CLI_LAYER, "path": None, "key": dotted}
        elif (origin := config.origin(dotted)) is not None:
            provenance[dotted] = origin
    return provenance


def apply_overrides(config: Config, raw_overrides: tuple[str, ...]) -> Config:
    """Deep-merge CLI overrides into a Config instance.

    Parses each raw override string, builds a nested override dict,
    and delegates to ``Config.with_overrides()`` for the merge.

    Args:
        config: Original immutable Config from file/env layers.
        raw_overrides: Tuple of ``SECTION.KEY=VALUE`` strings from ``--set``.

    Returns:
        New Config instance with overrides applied, or the original if
        ``raw_overrides`` is empty.

    Raises:
        ValueError: If any override string is malformed, or two of them conflict.

    Examples:
        >>> from lib_layered_config import Config
        >>> cfg = Config({"s": {"k": 1}}, {"s.k": {"layer": "default", "path": None, "key": "s.k"}})
        >>> result = apply_overrides(cfg, ("s.k=2",))
        >>> result["s"]["k"]
        2
        >>> result.origin("s.k")["layer"]
        'cli'
        >>> apply_overrides(cfg, ()) is cfg
        True
    """
    if not raw_overrides:
        return config

    overrides, overridden = nest_overrides(raw_overrides)

    # Rebuilt rather than returned straight from with_overrides, which shares
    # the original provenance map by design: the merged value is the CLI's and
    # its recorded origin still named the file it replaced, so `config` sent a
    # reader to a file holding the old value.
    merged = config.with_overrides(overrides)
    merged_as_dict = merged.as_dict()
    return Config(merged_as_dict, _provenance_naming_the_cli(config, merged_as_dict, overridden))


__all__ = [
    "CLI_LAYER",
    "CoercedValue",
    "ConfigOverride",
    "apply_overrides",
    "coerce_value",
    "nest_overrides",
    "parse_override",
]
