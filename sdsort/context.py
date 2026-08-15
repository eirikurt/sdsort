from __future__ import annotations

import tomllib
from ast import ImportFrom, Module
from dataclasses import dataclass
from functools import lru_cache
from itertools import takewhile
from typing import TYPE_CHECKING, Generic, TypeVar

if TYPE_CHECKING:
    from pathlib import Path

    from sdsort.block import FunctionBlock


@dataclass
class Context:
    deferred_annotations: bool
    visibility_ranks: VisibilityRanks[int | None] | None = None
    sort_by_name: bool = False

    @property
    def sort_by_visibility(self) -> bool:
        return self.visibility_ranks is not None


def gather_context(root_node: Module, file_path: Path | None = None) -> Context:
    imports = [statement for statement in root_node.body if isinstance(statement, ImportFrom)]
    deferred_annotations = any(
        imprt.module == "__future__" and any(alias.name == "annotations" for alias in imprt.names)
        for imprt in imports
    )

    if not deferred_annotations and file_path is not None:
        deferred_annotations = _targets_python314_or_newer(file_path.parent)

    return Context(deferred_annotations=deferred_annotations)


T = TypeVar("T", bound=int | None)


@dataclass(slots=True)
class VisibilityRanks(Generic[T]):
    """Configuration options for sorting logic based on visibility of method names on a given class.\\
        We use a TypeState pattern to avoid code duplication and ensure that the consumers of this class handle the expected state of the ranks."""

    dunder: T
    """A method name that starts and ends with double underscores (e.g. `__init__`)."""
    private: T
    """A method name with same prefix as a dunder, but no suffix (e.g. `__private`)."""
    protected: T
    """A method name that starts with a single underscore (e.g. `_protected`)."""
    public: T
    """Any method with no naming pattern corresponding to the above (e.g. `public`)."""

    def into_ok_or_default(self) -> VisibilityRanks[int]:
        """Transform a `VisibilityRanks[T]` into a `VisibilityRanks[int]` by replacing `None` values by a default value.\\
        The default value is the maximum of the non-`None` ranks plus one, so that any `None` rank is considered to be "after" all the other ranks."""
        ranks = (self.dunder, self.private, self.protected, self.public)
        default = max(rank for rank in ranks if rank is not None) + 1
        return VisibilityRanks[int](*(rank if rank is not None else default for rank in ranks))

    def into_sorted(self: VisibilityRanks[int]) -> list[int]:
        """De-duplicate and sort the ranks into a list of `int`, in ascending order.\\
        Used before storing the output in a `ClassBlock`."""
        return sorted({self.dunder, self.private, self.protected, self.public})

    def classify_for_block(self: VisibilityRanks[int], block: FunctionBlock, name: str):
        """Classify a `FunctionBlock` according to its name and assign it the corresponding rank."""
        if name.startswith("__"):
            if name.endswith("__"):
                block.rank = self.dunder
            else:
                block.rank = self.private
        elif name.startswith("_"):
            block.rank = self.protected
        else:
            block.rank = self.public


@lru_cache
def _targets_python314_or_newer(directory: Path) -> bool:
    pyproject = _find_pyproject(directory)
    if pyproject is None:
        return False
    return _requires_python314_or_newer(pyproject)


@lru_cache
def _requires_python314_or_newer(pyproject: Path) -> bool:
    with pyproject.open("rb") as f:
        data = tomllib.load(f)
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
