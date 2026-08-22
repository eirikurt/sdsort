from __future__ import annotations

import tomllib
from dataclasses import dataclass
from functools import lru_cache
from itertools import takewhile
from typing import TYPE_CHECKING, Any

from .config import Config

if TYPE_CHECKING:
    from pathlib import Path

TomlTable = dict[str, Any]


@dataclass(frozen=True)
class PyProject:
    """A pyproject.toml file, and everything sdsort reads out of one."""

    path: Path
    table: TomlTable

    @classmethod
    def nearest_to(cls, source_path: Path) -> PyProject | None:
        """The pyproject.toml governing `source_path`: the closest one at or above it, if any."""
        directory = source_path.parent
        for parent in [directory, *directory.parents]:
            candidate = parent / "pyproject.toml"
            if candidate.is_file():
                return cls(candidate, _load_table(candidate))
        return None

    @property
    def config(self) -> Config:
        """The `[tool.sdsort]` configuration, or the defaults where the table is absent.

        Raises `ConfigError` if the table holds anything sdsort cannot honour as written.
        """
        return Config.from_toml(self.table, self.path)

    @property
    def targets_python314_or_newer(self) -> bool:
        """Whether `requires-python` rules out every version that evaluates annotations eagerly."""
        return _targets_python314_or_newer(self.table)


@lru_cache
def _load_table(pyproject: Path) -> TomlTable:
    with pyproject.open("rb") as file:
        return tomllib.load(file)


def _targets_python314_or_newer(data: TomlTable) -> bool:
    specifier: str = data.get("project", {}).get("requires-python", "")
    for part in specifier.split(","):
        part = part.strip()
        if part.startswith(">="):
            version = part[2:].strip().split(".")
            if len(version) >= 2:
                major = _leading_int(version[0])
                minor = _leading_int(version[1])
                if major == 3 and minor >= 14:
                    return True
    return False


def _leading_int(text: str) -> int:
    """Parse the leading integer of a version segment.

    PEP 440 permits pre-release specifiers in requires-python (e.g. ">=3.14a1"), so a
    segment like "14a1" must not be passed to int() directly. Returns 0 when there is
    no leading digit.
    """
    digits = "".join(takewhile(str.isdigit, text))
    return int(digits) if digits else 0
