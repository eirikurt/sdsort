from _ast import ClassDef, Module, FunctionDef
from ast import walk, Call, Attribute
from collections import defaultdict
from typing import Iterable, Dict, List

import ast


def step_down_sort(python_file_path: str) -> str:
    #
    source = _read_file(python_file_path)
    syntax_tree = ast.parse(source, filename=python_file_path)
    source_lines = source.splitlines()
    modified_lines = []

    for cls in _find_classes(syntax_tree):
        modified_lines.extend(source_lines[len(modified_lines) : cls.lineno])
        modified_lines.extend(_sort_methods_within_class(source_lines, cls))
    modified_lines.extend(source_lines[len(modified_lines) :])
    # TODO: Don't write updated file unless methods were moved
    # TODO: remove astor dependency?
    return "\n".join(modified_lines) + "\n"


def _read_file(file_path: str) -> str:
    with open(file_path) as f:
        source = f.read()
    # TODO: is this carriage return ceremony needed?
    source = source.replace("\r\n", "\n").replace("\r", "\n")
    if not source.endswith("\n"):
        source += "\n"
    return source


def _find_classes(syntax_tree: Module) -> Iterable[ClassDef]:
    for node in syntax_tree.body:
        if isinstance(node, ClassDef):
            yield node


def _sort_methods_within_class(
    source_lines: List[str], class_def: ClassDef
) -> List[str]:
    # Find methods
    methods = [node for node in class_def.body if isinstance(node, FunctionDef)]
    method_dict = {m.name: m for m in methods}

    # Build dependency graph among methods
    dependencies = _find_dependencies(methods)

    # Re-order methods as needed
    sorted_dict = {}
    for method_name in method_dict:
        _depth_first_sort(method_name, method_dict, dependencies, sorted_dict)
    print(sorted_dict.keys())
    result = source_lines[class_def.lineno : methods[0].lineno - 1]
    for method in sorted_dict.values():
        following_methods = [m.lineno for m in methods if m.lineno > method.lineno]
        if len(following_methods) > 0:
            stop = min(following_methods) - 1
        else:
            stop = max(n.lineno for n in walk(method) if hasattr(n, "lineno"))
        result.extend(source_lines[method.lineno - 1 : stop])
    return result


def _find_dependencies(methods: List[FunctionDef]) -> Dict[str, List[str]]:
    dependencies = defaultdict(list)
    method_names = set((m.name for m in methods))
    for method in methods:
        for node in walk(method):
            if isinstance(node, Call) and isinstance(node.func, Attribute):
                target = node.func.attr
                if target in method_names and target not in dependencies[method.name]:
                    dependencies[method.name].append(target)
    return dependencies


def _depth_first_sort(
    current_method_name: str,
    method_dict: Dict[str, FunctionDef],
    dependencies: Dict[str, List[str]],
    sorted_dict: Dict[str, FunctionDef],
):
    # Rely on the fact that dicts maintain insertion order as of Python 3.7
    method = sorted_dict.pop(current_method_name, method_dict[current_method_name])
    sorted_dict[current_method_name] = method
    for dependency in dependencies[current_method_name]:
        # TODO: Detect/break cycles
        _depth_first_sort(dependency, method_dict, dependencies, sorted_dict)
