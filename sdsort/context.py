from __future__ import annotations

import tomllib
from ast import ImportFrom, Module
from dataclasses import dataclass
from functools import lru_cache
from itertools import takewhile
from typing import TYPE_CHECKING, Any, TypeVar

from .visibility import VisibilityRanks

if TYPE_CHECKING:
    from pathlib import Path

    TomlTable = dict[str, Any]


T = TypeVar("T", bound=int | None)


@dataclass
class Context:
    deferred_annotations: bool
    """Whether lazy annotations are enabled or not."""
    visibility_ranks: VisibilityRanks[int | None] | None = None
    """Configuration options for sorting logic based on visibility of method names on a given class."""
    sort_by_name: bool = False
    """If `True`, sort methods by name after sorting by visibility.\\
    Default is `False`."""

    @property
    def sort_by_visibility(self) -> bool:
        return self.visibility_ranks is not None


def gather_context(root_node: Module, file_path: Path | None = None) -> Context:
    imports = (statement for statement in root_node.body if isinstance(statement, ImportFrom))
    deferred_annotations = any(
        imprt.module == "__future__" and any(alias.name == "annotations" for alias in imprt.names)
        for imprt in imports
    )
    config, deferred_annotations = _get_config_and_annotations(file_path, deferred_annotations)
    return Context(deferred_annotations, VisibilityRanks.try_from(config), config.get("sort-by-name", False))


@lru_cache
def _get_config_and_annotations(file_path: Path | None, deferred_annotations: bool) -> tuple[TomlTable, bool]:
    match file_path:
        case None:
            return {}, deferred_annotations
        case path:
            return _handle_pyproject(path, deferred_annotations)


def _handle_pyproject(file_path: Path, deferred_annotations: bool) -> tuple[TomlTable, bool]:
    match _find_pyproject(file_path.parent):
        case None:
            return {}, deferred_annotations
        case pyproject:
            with pyproject.open("rb") as f:
                data = tomllib.load(f)
                config: TomlTable = data.get("tool", {}).get("sdsort", {})
                if not deferred_annotations:
                    deferred_annotations = _targets_python314_or_newer(data)
            return config, deferred_annotations


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


def _find_pyproject(directory: Path) -> Path | None:
    for parent in [directory, *directory.parents]:
        candidate = parent / "pyproject.toml"
        if candidate.is_file():
            return candidate
    return None
