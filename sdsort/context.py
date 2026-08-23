from __future__ import annotations

from ast import ImportFrom, Module
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .config import Config
from .pyproject import PyProject

if TYPE_CHECKING:
    from pathlib import Path


@dataclass
class Context:
    deferred_annotations: bool
    config: Config = field(default_factory=Config)


def gather_context(root_node: Module, file_path: Path | None = None) -> Context:
    deferred_annotations = _imports_future_annotations(root_node)
    pyproject = PyProject.nearest_to(file_path) if file_path is not None else None
    if pyproject is None:
        return Context(deferred_annotations)
    return Context(
        deferred_annotations or pyproject.targets_python314_or_newer,
        pyproject.config,
    )


def _imports_future_annotations(root_node: Module) -> bool:
    imports = (statement for statement in root_node.body if isinstance(statement, ImportFrom))
    return any(
        imprt.module == "__future__" and any(alias.name == "annotations" for alias in imprt.names)
        for imprt in imports
    )
