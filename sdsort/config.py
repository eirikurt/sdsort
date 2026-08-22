from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Literal

MethodOrderAttribute = Literal["dependency", "visibility", "name"]
MethodVisibility = Literal["dunder", "public", "protected", "private"]


@dataclass(frozen=True)
class Config:
    method_order: list[MethodOrderAttribute] = field(default_factory=lambda: ["dependency"])
    visibility_order: list[MethodVisibility | Literal["*"]] = field(
        default_factory=lambda: ["dunder", "public", "protected", "private"]
    )

    @classmethod
    def from_toml(cls, toml: dict[str, Any]):
        default_config = cls.default()
        table = toml.get("tool", {}).get("sdsort", {})
        return Config(
            method_order=table.get("method-order", default_config.method_order),
            visibility_order=table.get("visibility-order", default_config.visibility_order),
        )

    @classmethod
    @lru_cache(maxsize=1)
    def default(cls):
        return cls()
