from ast import ImportFrom, Module
from dataclasses import dataclass


@dataclass
class Context:
    deferred_annotations: bool


def gather_context(root_node: Module):
    imports = [statement for statement in root_node.body if isinstance(statement, ImportFrom)]
    deferred_annotations = any(
        imprt.module == "__future__" and any(alias.name == "annotations" for alias in imprt.names)
        for imprt in imports
    )

    # TODO: check if we are in Python 3.14+ mode
    return Context(deferred_annotations=deferred_annotations)
