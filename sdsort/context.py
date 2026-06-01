import tomllib
from ast import ImportFrom, Module
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass
class Context:
    deferred_annotations: bool


def gather_context(root_node: Module, file_path: Path | None = None) -> Context:
    imports = [statement for statement in root_node.body if isinstance(statement, ImportFrom)]
    deferred_annotations = any(
        imprt.module == "__future__" and any(alias.name == "annotations" for alias in imprt.names)
        for imprt in imports
    )

    if not deferred_annotations and file_path is not None:
        deferred_annotations = _targets_python314_or_newer(file_path.parent)

    return Context(deferred_annotations=deferred_annotations)


@lru_cache
def _targets_python314_or_newer(directory: Path) -> bool:
    pyproject = _find_pyproject(directory)
    if pyproject is None:
        return False
    with pyproject.open("rb") as f:
        data = tomllib.load(f)
    specifier: str = data.get("project", {}).get("requires-python", "")
    for part in specifier.split(","):
        part = part.strip()
        if part.startswith(">="):
            version = part[2:].strip().split(".")
            if len(version) >= 2 and int(version[0]) == 3 and int(version[1]) >= 14:
                return True
    return False


def _find_pyproject(directory: Path) -> Path | None:
    for parent in [directory, *directory.parents]:
        candidate = parent / "pyproject.toml"
        if candidate.is_file():
            return candidate
    return None
