from _ast import ClassDef, Module, FunctionDef
from ast import walk, Call, Attribute
from collections import defaultdict
from typing import Iterable, Dict, List

import astor


def step_down_sort(python_file_path: str) -> str:
    #
    ast = astor.parse_file(python_file_path)
    for cls in _find_classes(ast):
        _sort_methods_within_class(cls)
    # TODO: Don't generate code unless methods were moved
    # XXX: avoid code gen, just shift ranges of lines instead?
    return astor.code_gen.to_source(ast)


def _find_classes(ast: Module) -> Iterable[ClassDef]:
    for node in ast.body:
        if isinstance(node, ClassDef):
            yield node


def _sort_methods_within_class(class_def: ClassDef) -> None:
    # Find methods
    methods = [node for node in class_def.body if isinstance(node, FunctionDef)]

    # Build dependency graph among methods
    dependencies = _find_dependencies(methods)
    # Detect/break cycles
    # Re-order methods as needed
    for last in range(len(methods) - 1, -1, -1):
        for i in range(last):
            j = i + 1
            method_i = methods[i].name
            method_j = methods[j].name
            if method_i in dependencies[method_j]:
                _swap(class_def, methods, i, j)


def _find_dependencies(methods: List[FunctionDef]) -> Dict[str, List[str]]:
    dependencies = defaultdict(list)
    method_names = set((m.name for m in methods))
    for method in methods:
        for node in walk(method):
            if isinstance(node, Call) and isinstance(node.func, Attribute):
                target = node.func.attr
                if target in method_names:
                    dependencies[method.name].append(target)
    return dependencies


def _swap(class_def: ClassDef, methods: List[FunctionDef], i: int, j: int):
    going_down = methods[i]
    going_up = methods[j]
    methods[i] = going_up
    methods[j] = going_down

    i_pos_in_class = class_def.body.index(going_down)
    j_pos_in_class = class_def.body.index(going_up)
    class_def.body[i_pos_in_class] = going_up
    class_def.body[j_pos_in_class] = going_down

