import os
from ast import AST, AsyncFunctionDef, Attribute, Call, ClassDef, FunctionDef, Module, Name, parse, walk
from collections import defaultdict
from glob import glob
from typing import Callable, Dict, Iterable, List, Optional, Protocol, Tuple, TypeGuard, Union

import click

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
                file.write(modified_source)
            click.echo(f"{file_path} is all sorted")
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

    # First, sort top-level functions
    modified_lines = _sort_top_level_functions(source_lines, syntax_tree)

    # Re-parse to get updated line numbers for class sorting
    modified_source = "\n".join(modified_lines) + "\n"
    modified_tree = parse(modified_source)

    # Then, sort methods within classes
    final_lines: List[str] = []
    for cls in _find_classes(modified_tree):
        # Copy everything, which hasn't been copied so far, up until the class def,
        final_lines.extend(modified_lines[len(final_lines) : cls.lineno])

        # Copy class after sorting its methods
        final_lines.extend(_sort_methods_within_class(modified_lines, cls))

    # Copy remainder of file
    final_lines.extend(modified_lines[len(final_lines) :])

    if source_lines != final_lines:
        return "\n".join(final_lines) + "\n"
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


def _sort_top_level_functions(source_lines: List[str], syntax_tree: Module) -> List[str]:
    """Sort top-level functions according to step-down rule."""
    func_dict = _find_top_level_functions(syntax_tree)

    if not func_dict:
        return source_lines

    # Barriers (module-level code that calls functions) divide the file into zones.
    # Functions within each zone are sorted independently, ensuring that functions
    # called at module level remain defined before the barrier that calls them.
    barrier_line_numbers = sorted(line_no for line_no, _ in _find_barriers(syntax_tree, func_dict))

    sorted_dict: Dict[str, FunDef] = {}
    for zone_funcs in _group_by_zone(func_dict, source_lines, barrier_line_numbers):
        deps = _find_dependencies(zone_funcs, _function_call_target)
        zone_sorted: Dict[str, FunDef] = {}
        for name in zone_funcs:
            _depth_first_sort(name, zone_funcs, deps, zone_sorted, [])
        sorted_dict.update(zone_sorted)

    return _rearrange_top_level_functions(source_lines, func_dict, sorted_dict)


def _find_top_level_functions(syntax_tree: Module) -> Dict[str, FunDef]:
    return {node.name: node for node in syntax_tree.body if isinstance(node, (FunctionDef, AsyncFunctionDef))}


def _find_barriers(syntax_tree: Module, functions: Dict[str, FunDef]) -> List[Tuple[int, set[str]]]:
    """Find module-level statements that call functions directly.

    Returns a list of (line_number, set of function names called) for each barrier.
    A barrier is any non-function-def statement that invokes a function.
    """
    barriers: List[Tuple[int, set[str]]] = []
    for node in syntax_tree.body:
        if isinstance(node, (FunctionDef, AsyncFunctionDef, ClassDef)):
            continue

        called_funcs: set[str] = set()
        for child in walk(node):
            if isinstance(child, Call) and isinstance(child.func, Name):
                if child.func.id in functions:
                    called_funcs.add(child.func.id)

        if called_funcs:
            barriers.append((node.lineno, called_funcs))

    return barriers


def _group_by_zone(
    func_dict: Dict[str, FunDef], source_lines: List[str], barrier_line_numbers: List[int]
) -> Iterable[Dict[str, FunDef]]:
    """Group functions into zones separated by barrier lines.

    Each zone contains the functions that appear between two consecutive barriers
    (or before the first / after the last). Functions within a zone can be freely
    reordered without crossing a barrier.
    """
    zones: list[Dict[str, FunDef]] = [{} for _ in range(len(barrier_line_numbers) + 1)]
    for name, func in func_dict.items():
        func_start = _determine_line_range(func, source_lines)[0]
        # barrier_lines are 1-based (AST), func_start is 0-based — the off-by-one
        # means `<` is the correct comparison (a function at 0-based line N is before
        # a barrier at 1-based line N+1).
        zone_idx = next(
            (i for i, bl in enumerate(barrier_line_numbers) if func_start < bl), len(barrier_line_numbers)
        )
        zones[zone_idx][name] = func
    return [z for z in zones if z]


def _rearrange_top_level_functions(
    source_lines: List[str],
    func_dict: Dict[str, FunDef],
    sorted_dict: Dict[str, FunDef],
) -> List[str]:
    """Rearrange top-level code with sorted functions."""
    result, pos = _rearrange_functions(source_lines, func_dict, sorted_dict)
    result.extend(source_lines[pos:])
    return result


def _sort_methods_within_class(source_lines: List[str], class_def: ClassDef) -> List[str]:
    # TODO: recursively sort methods within nested classes?

    # Find methods
    method_dict = {node.name: node for node in class_def.body if isinstance(node, (FunctionDef, AsyncFunctionDef))}

    # Build dependency graph among methods
    dependencies = _find_dependencies(method_dict, _method_call_target)

    # Re-order methods as needed
    sorted_dict: Dict[str, FunDef] = {}
    for method_name in method_dict:
        _depth_first_sort(method_name, method_dict, dependencies, sorted_dict, [])

    # Copy lines from the original source, shifting the methods around as needed
    return _rearrange_class_code(class_def, method_dict, sorted_dict, source_lines)


def _find_dependencies(
    funcs: Dict[str, FunDef],
    get_call_target: Callable[[Call], Optional[str]],
) -> Dict[str, List[str]]:
    """Find dependencies between functions/methods based on call patterns.

    Note: For top-level functions, decorators are not included as dependencies.
    Decorators must be defined before use (syntactic constraint), but for step-down
    ordering, the decorated function should come before its decorator.
    """
    dependencies: Dict[str, List[str]] = defaultdict(list)
    for func in funcs.values():
        for node in walk(func):
            if isinstance(node, Call):
                target = get_call_target(node)
                if target is not None and target in funcs and target not in dependencies[func.name]:
                    dependencies[func.name].append(target)
    return dependencies


def _method_call_target(node: Call) -> Optional[str]:
    """Extract target name from self.method() calls."""
    return node.func.attr if isinstance(node.func, Attribute) else None


def _function_call_target(node: Call) -> Optional[str]:
    """Extract target name from direct function() calls."""
    return node.func.id if isinstance(node.func, Name) else None


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
    result, _ = _rearrange_functions(source_lines, method_dict, sorted_dict, start=class_def.lineno)
    return result


def _rearrange_functions(
    source_lines: List[str],
    func_dict: Dict[str, FunDef],
    sorted_dict: Dict[str, FunDef],
    start: int = 0,
) -> Tuple[List[str], int]:
    """Rearrange source lines by swapping functions from their original positions to sorted positions."""
    result: List[str] = []
    source_position = start
    for original, replacement in zip(func_dict.values(), sorted_dict.values()):
        original_range = _determine_line_range(original, source_lines)
        replacement_range = _determine_line_range(replacement, source_lines)
        result.extend(source_lines[source_position : original_range[0]])
        result.extend(source_lines[replacement_range[0] : replacement_range[1]])
        source_position = original_range[1]
    return result, source_position


def _determine_line_range(method: FunDef, source_lines: List[str]) -> Tuple[int, int]:
    start = method.lineno
    if len(method.decorator_list) > 0:
        start = min(d.lineno for d in method.decorator_list)

    # AST line numbers are 1-based. Subtract one from the start position to make it 0-based
    start -= 1

    # Check if there are any leading comments. If so, include them as well
    peek = source_lines[start - 1] if start > 0 else ""
    while peek.strip().startswith("#"):
        start -= 1
        peek = source_lines[start - 1] if start > 0 else ""

    stop = max(n.lineno for n in walk(method) if has_lineno(n))

    # Probe a bit further until we find an empty line or one with less indentation than the method body
    peek = source_lines[stop] if stop < len(source_lines) else ""
    while peek.strip() != "" and (
        peek.startswith(" " * (method.col_offset + 1)) or peek.startswith("\t" * (method.col_offset + 1))
    ):
        stop += 1
        peek = source_lines[stop] if stop < len(source_lines) else ""

    return start, stop


class HasLineNo(Protocol):
    lineno: int


def has_lineno(node: AST) -> TypeGuard[HasLineNo]:
    return hasattr(node, "lineno")
