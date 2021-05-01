import os
from ast import AsyncFunctionDef, Attribute, Call, ClassDef, FunctionDef, Module, parse, walk
from collections import defaultdict
from glob import glob
from typing import Dict, Iterable, List, Optional, Tuple, Union

import click

# TODO: proper help for CLI
# TODO: report what files were processed
# TODO: reject files that are not python files
# TODO: Don't write updated file unless methods were moved

FunDef = Union[FunctionDef, AsyncFunctionDef]


@click.command()
@click.argument(
    "paths",
    nargs=-1,
    type=click.Path(exists=True, file_okay=True, dir_okay=True, readable=True),
    is_eager=True,
)
def main(paths: Tuple[str, ...]):
    file_paths = _expand_file_paths(paths)
    for file_path in sorted(file_paths):
        modified_source = step_down_sort(file_path)
        if modified_source is not None:
            with open(file_path, "w") as file:
                click.echo(f"{file_path} is all sorted")
                file.write(modified_source)
        else:
            click.echo(f"{file_path} is unchanged")


def _expand_file_paths(paths: Tuple[str, ...]) -> Iterable[str]:
    file_paths = []
    for path in paths:
        if os.path.isdir(path):
            file_paths.extend(glob(os.path.join(path, "**/*.py"), recursive=True))
        else:
            file_paths.append(path)
    return file_paths


def step_down_sort(python_file_path: str) -> Optional[str]:
    source = _read_file(python_file_path)
    syntax_tree = parse(source, filename=python_file_path)
    source_lines = source.splitlines()

    modified_lines: List[str] = []
    for cls in _find_classes(syntax_tree):
        # Copy everything, which hasn't been copied so far, up until the class def,
        modified_lines.extend(source_lines[len(modified_lines) : cls.lineno])

        # Copy class after sorting its methods
        modified_lines.extend(_sort_methods_within_class(source_lines, cls))

    # Copy remainder of file
    modified_lines.extend(source_lines[len(modified_lines) :])

    if source_lines != modified_lines:
        return "\n".join(modified_lines) + "\n"
    else:
        return None


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


def _sort_methods_within_class(source_lines: List[str], class_def: ClassDef) -> List[str]:
    # TODO: recursively sort methods within nested classes?

    # Find methods
    method_dict = {
        node.name: node
        for node in class_def.body
        if isinstance(node, FunctionDef) or isinstance(node, AsyncFunctionDef)
    }

    # Build dependency graph among methods
    dependencies = _find_dependencies(method_dict)

    # Re-order methods as needed
    sorted_dict: Dict[str, FunDef] = {}
    for method_name in method_dict:
        _depth_first_sort(method_name, method_dict, dependencies, sorted_dict, [])

    # Copy lines from the original source, shifting the methods around as needed
    return _rearrange_class_code(class_def, method_dict, sorted_dict, source_lines)


def _find_dependencies(methods: Dict[str, FunDef]) -> Dict[str, List[str]]:
    dependencies: Dict[str, List[str]] = defaultdict(list)
    for method in methods.values():
        for node in walk(method):
            if isinstance(node, Call) and isinstance(node.func, Attribute):
                target = node.func.attr
                if target in methods and target not in dependencies[method.name]:
                    dependencies[method.name].append(target)
    return dependencies


def _depth_first_sort(
    current_method_name: str,
    method_dict: Dict[str, FunDef],
    dependencies: Dict[str, List[str]],
    sorted_dict: Dict[str, FunDef],
    path: List[str],
):
    path.append(current_method_name)

    # Rely on the fact that dicts maintain insertion order as of Python 3.7
    method = sorted_dict.pop(current_method_name, method_dict[current_method_name])
    sorted_dict[current_method_name] = method
    for dependency in dependencies[current_method_name]:
        if dependency not in path:
            _depth_first_sort(dependency, method_dict, dependencies, sorted_dict, path)

    path.pop()


def _rearrange_class_code(
    class_def: ClassDef,
    method_dict: Dict[str, FunDef],
    sorted_dict: Dict[str, FunDef],
    source_lines: List[str],
) -> List[str]:
    source_position = class_def.lineno
    result = []
    for original_method, replacement_method in zip(method_dict.values(), sorted_dict.values()):
        original_method_range = _determine_line_range(original_method, source_lines)
        replacement_method_range = _determine_line_range(replacement_method, source_lines)

        # Add everything, that hasn't been copied so far, up to where the original method starts
        result.extend(source_lines[source_position : original_method_range[0]])

        # Copy the replacement method
        result.extend(source_lines[replacement_method_range[0] : replacement_method_range[1]])

        # Move the position cursor to where the original method ended
        source_position = original_method_range[1]
    return result


def _determine_line_range(method: FunDef, source_lines: List[str]) -> Tuple[int, int]:
    start = method.lineno
    if len(method.decorator_list) > 0:
        start = min(d.lineno for d in method.decorator_list)
    stop = max(n.lineno for n in walk(method) if hasattr(n, "lineno"))

    # Probe a bit further until we find an empty line or one with less indentation than the method body
    peek = source_lines[stop] if stop < len(source_lines) else ""
    while peek.strip() != "" and (
        peek.startswith(" " * (method.col_offset + 1)) or peek.startswith("\t" * (method.col_offset + 1))
    ):
        stop += 1
        peek = source_lines[stop] if stop < len(source_lines) else ""

    # AST line numbers are 1-based. Subtract one from the start position to make it 0-based
    # The stop position is exclusive (making this a half-open range) so leave it as is.
    return start - 1, stop
