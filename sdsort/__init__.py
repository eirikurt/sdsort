import ast
from ast import AsyncFunctionDef, Attribute, Call, ClassDef, FunctionDef, Module, walk
from collections import defaultdict
from typing import Dict, Iterable, List, Tuple

# TODO: command line utility that modifies a file
# TODO: Don't write updated file unless methods were moved
# TODO: ability to scan a folder recursively and rearrange all *.py files


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
    methods = [
        node
        for node in class_def.body
        if isinstance(node, FunctionDef) or isinstance(node, AsyncFunctionDef)
    ]
    method_dict = {m.name: m for m in methods}

    # Build dependency graph among methods
    dependencies = _find_dependencies(methods)

    # Re-order methods as needed
    sorted_dict = {}
    for method_name in method_dict:
        _depth_first_sort(method_name, method_dict, dependencies, sorted_dict)

    # Copy lines from the original source, shifting the methods around as needed
    source_position = class_def.lineno
    result = []
    for original_method, replacement_method in zip(methods, sorted_dict.values()):
        original_method_range = _determine_line_range(original_method)
        replacement_method_range = _determine_line_range(replacement_method)

        # Add everything, that hasn't been copied so far, up to where the original method starts
        result.extend(source_lines[source_position : original_method_range[0]])

        # Copy the replacement method
        result.extend(
            source_lines[replacement_method_range[0] : replacement_method_range[1]]
        )

        # Move the position cursor to where the original method ended
        source_position = original_method_range[1]
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


def _determine_line_range(method: FunctionDef) -> Tuple[int, int]:
    start = method.lineno
    if len(method.decorator_list) > 0:
        start = min(d.lineno for d in method.decorator_list)
    stop = max(n.lineno for n in walk(method) if hasattr(n, "lineno"))
    # TODO: probe a bit further until we find a line with less indentation?
    return start - 1, stop
