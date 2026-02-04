import os
from ast import AST, AsyncFunctionDef, Attribute, Call, ClassDef, FunctionDef, Module, Name, parse, walk
from collections import defaultdict
from glob import glob
from typing import Dict, Iterable, List, Optional, Protocol, Tuple, TypeGuard, Union

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


def _find_top_level_functions(syntax_tree: Module) -> Dict[str, FunDef]:
    return {
        node.name: node
        for node in syntax_tree.body
        if isinstance(node, FunctionDef) or isinstance(node, AsyncFunctionDef)
    }


def _find_barriers(syntax_tree: Module, functions: Dict[str, FunDef]) -> List[Tuple[int, set[str]]]:
    """Find module-level statements that call functions directly.

    Returns a list of (line_number, set of function names called) for each barrier.
    A barrier is any non-function-def statement that invokes a function.
    """
    barriers: List[Tuple[int, set[str]]] = []
    for node in syntax_tree.body:
        # Skip function and class definitions - they're not barriers
        if isinstance(node, (FunctionDef, AsyncFunctionDef, ClassDef)):
            continue

        # Find all function calls in this statement
        called_funcs: set[str] = set()
        for child in walk(node):
            if isinstance(child, Call) and isinstance(child.func, Name):
                if child.func.id in functions:
                    called_funcs.add(child.func.id)

        if called_funcs:
            barriers.append((node.lineno, called_funcs))

    return barriers


def _sort_top_level_functions(source_lines: List[str], syntax_tree: Module) -> List[str]:
    """Sort top-level functions according to step-down rule."""
    func_dict = _find_top_level_functions(syntax_tree)

    if not func_dict:
        return source_lines

    barriers = _find_barriers(syntax_tree, func_dict)

    # Find which functions are pinned (called at module level before their natural sort position)
    pinned_funcs: set[str] = set()
    for _, called_funcs in barriers:
        pinned_funcs.update(called_funcs)

    # Separate pinned and free functions
    # Pinned functions stay in their original position relative to barriers
    # Free functions are sorted together

    if not barriers:
        # Simple case: no barriers, sort all functions together
        return _sort_functions_in_region(source_lines, syntax_tree, func_dict)

    # Complex case: there are barriers
    # Strategy: keep pinned functions before their barrier, sort free functions
    return _sort_functions_with_barriers(source_lines, syntax_tree, func_dict, barriers, pinned_funcs)


def _sort_functions_in_region(
    source_lines: List[str], syntax_tree: Module, func_dict: Dict[str, FunDef]
) -> List[str]:
    """Sort all functions in a region with no barriers."""
    # Build dependency graph
    dependencies = _find_function_dependencies(func_dict)

    # Sort using depth-first traversal
    sorted_dict: Dict[str, FunDef] = {}
    for func_name in func_dict:
        _depth_first_sort(func_name, func_dict, dependencies, sorted_dict, [])

    # Rearrange source lines
    return _rearrange_top_level_code(source_lines, syntax_tree, func_dict, sorted_dict)


def _sort_functions_with_barriers(
    source_lines: List[str],
    syntax_tree: Module,
    func_dict: Dict[str, FunDef],
    barriers: List[Tuple[int, set[str]]],
    pinned_funcs: set[str],
) -> List[str]:
    """Sort functions while respecting barrier constraints."""
    # Find the first barrier line
    first_barrier_line = min(line for line, _ in barriers)

    # Separate functions into: before-barrier (pinned) and after-barrier (free)
    before_barrier: Dict[str, FunDef] = {}
    after_barrier: Dict[str, FunDef] = {}

    for name, func in func_dict.items():
        func_end = _determine_line_range(func, source_lines)[1]
        if name in pinned_funcs and func_end <= first_barrier_line:
            before_barrier[name] = func
        else:
            after_barrier[name] = func

    # Sort the after-barrier functions
    if after_barrier:
        dependencies = _find_function_dependencies(after_barrier)
        sorted_after: Dict[str, FunDef] = {}
        for func_name in after_barrier:
            _depth_first_sort(func_name, after_barrier, dependencies, sorted_after, [])
    else:
        sorted_after = {}

    # Build the result by copying content and swapping functions in their slots
    result: List[str] = []
    source_position = 0

    # Get lists of original and sorted after-barrier functions
    after_original = list(after_barrier.values())
    after_sorted = list(sorted_after.values())

    for node in syntax_tree.body:
        if isinstance(node, (FunctionDef, AsyncFunctionDef)):
            func_range = _determine_line_range(node, source_lines)
            if node.name in before_barrier:
                # Copy everything up to and including this pinned function
                result.extend(source_lines[source_position : func_range[1]])
                source_position = func_range[1]
            elif node.name in after_barrier:
                # Find this function's position in the original list
                orig_idx = next(i for i, f in enumerate(after_original) if f.name == node.name)

                # Copy everything up to where this function starts (spacing before it)
                result.extend(source_lines[source_position : func_range[0]])

                # Copy the replacement function (from sorted list at same index)
                replacement_func = after_sorted[orig_idx]
                replacement_range = _determine_line_range(replacement_func, source_lines)
                result.extend(source_lines[replacement_range[0] : replacement_range[1]])

                # Move past this original function
                source_position = func_range[1]

    # Copy any remaining content
    result.extend(source_lines[source_position:])

    return result


def _rearrange_top_level_code(
    source_lines: List[str],
    syntax_tree: Module,
    func_dict: Dict[str, FunDef],
    sorted_dict: Dict[str, FunDef],
) -> List[str]:
    """Rearrange top-level code with sorted functions."""
    result: List[str] = []
    source_position = 0

    # Get list of original and sorted functions
    original_funcs = list(func_dict.values())
    sorted_funcs = list(sorted_dict.values())

    for original_func, replacement_func in zip(original_funcs, sorted_funcs):
        original_range = _determine_line_range(original_func, source_lines)
        replacement_range = _determine_line_range(replacement_func, source_lines)

        # Copy everything up to where the original function starts
        result.extend(source_lines[source_position : original_range[0]])

        # Copy the replacement function
        result.extend(source_lines[replacement_range[0] : replacement_range[1]])

        # Move position to end of original function
        source_position = original_range[1]

    # Copy remaining content
    result.extend(source_lines[source_position:])

    return result


def _sort_methods_within_class(source_lines: List[str], class_def: ClassDef) -> List[str]:
    # TODO: recursively sort methods within nested classes?

    # Find methods
    method_dict = {
        node.name: node
        for node in class_def.body
        if isinstance(node, FunctionDef) or isinstance(node, AsyncFunctionDef)
    }

    # Build dependency graph among methods
    dependencies = _find_method_dependencies(method_dict)

    # Re-order methods as needed
    sorted_dict: Dict[str, FunDef] = {}
    for method_name in method_dict:
        _depth_first_sort(method_name, method_dict, dependencies, sorted_dict, [])

    # Copy lines from the original source, shifting the methods around as needed
    return _rearrange_class_code(class_def, method_dict, sorted_dict, source_lines)


def _find_method_dependencies(methods: Dict[str, FunDef]) -> Dict[str, List[str]]:
    """Find dependencies between methods (self.method() calls)."""
    dependencies: Dict[str, List[str]] = defaultdict(list)
    for method in methods.values():
        for node in walk(method):
            if isinstance(node, Call) and isinstance(node.func, Attribute):
                target = node.func.attr
                if target in methods and target not in dependencies[method.name]:
                    dependencies[method.name].append(target)
    return dependencies


def _find_function_dependencies(functions: Dict[str, FunDef]) -> Dict[str, List[str]]:
    """Find dependencies between top-level functions (direct function() calls).

    Note: Decorators are not included as dependencies because they have different semantics.
    Decorators must be defined before use (syntactic constraint), but for step-down ordering,
    the decorated function should come before its decorator (conceptually).
    We rely on valid Python input where decorators are already defined before use.
    """
    dependencies: Dict[str, List[str]] = defaultdict(list)
    for func in functions.values():
        for node in walk(func):
            if isinstance(node, Call) and isinstance(node.func, Name):
                target = node.func.id
                if target in functions and target not in dependencies[func.name]:
                    dependencies[func.name].append(target)
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
    stop = max(n.lineno for n in walk(method) if has_lineno(n))

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


class HasLineNo(Protocol):
    lineno: int


def has_lineno(node: AST) -> TypeGuard[HasLineNo]:
    return hasattr(node, "lineno")
