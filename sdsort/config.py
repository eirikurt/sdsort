from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import TYPE_CHECKING, Any, Final, Literal, cast, get_args

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path


MethodOrderAttribute = Literal["call", "visibility", "name"]
MethodVisibility = Literal["dunder", "public", "protected", "private"]

ALLOWED_VALUES: Final[dict[str, tuple[str, ...]]] = {
    "method-order": get_args(MethodOrderAttribute),
    "visibility-order": (*get_args(MethodVisibility), "*"),
}
"""Every value each `[tool.sdsort]` key accepts, keyed by the key that accepts it."""


@dataclass(frozen=True)
class Config:
    method_order: Sequence[MethodOrderAttribute] = field(default_factory=lambda: ["call"])
    visibility_order: Sequence[MethodVisibility | Literal["*"]] = field(
        default_factory=lambda: ["dunder", "public", "protected", "private"]
    )

    @classmethod
    def from_toml(cls, toml: dict[str, Any], source: Path | None = None):
        table = _sdsort_table(toml, source)
        default_config = cls.default()
        return Config(
            method_order=table.get("method-order", default_config.method_order),
            visibility_order=table.get("visibility-order", default_config.visibility_order),
        )

    @classmethod
    @lru_cache(maxsize=1)
    def default(cls):
        return cls()


class ConfigError(Exception):
    """Raised when a `[tool.sdsort]` table cannot be honoured as written."""


def _sdsort_table(toml: dict[str, Any], source: Path | None) -> dict[str, Any]:
    table = _sub_table(_sub_table(toml, "tool"), "sdsort")
    problems = _find_problems(table)
    if problems:
        location = f" in {source}" if source is not None else ""
        raise ConfigError(f"invalid sdsort configuration{location}:\n  " + "\n  ".join(problems))
    return cast("dict[str, Any]", table)


def _sub_table(value: object, key: str) -> object:
    if not isinstance(value, dict):
        return value
    table = cast("dict[str, object]", value)
    return table[key] if key in table else {}


def _find_problems(table: object) -> list[str]:
    if not isinstance(table, dict):
        return [f"[tool.sdsort]: must be a table, not {type(table).__name__}"]
    settings = cast("dict[str, object]", table)
    problems = [f"unknown key '{key}'" for key in settings if key not in ALLOWED_VALUES]
    for key, allowed in ALLOWED_VALUES.items():
        if key not in settings:
            continue
        value = settings[key]
        if not isinstance(value, list):
            problems.append(f"{key}: must be a list of strings, not {type(value).__name__}")
            continue
        entries = cast("list[object]", value)
        problems.extend(f"{key}: unknown value '{entry}'" for entry in entries if entry not in allowed)
        problems.extend(
            f"{key}: duplicate value '{entry}'" for index, entry in enumerate(entries) if entry in entries[:index]
        )
    return problems
