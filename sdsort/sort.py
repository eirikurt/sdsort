from ast import AsyncFunctionDef, Attribute, Call, ClassDef, FunctionDef, Module, Name, parse, walk
from collections import defaultdict
from itertools import chain, takewhile
from pathlib import Path
from typing import Callable, Iterable, Optional

from .format import normalize_blank_lines
from .utils.ast import (
    Function,
    determine_line_range,
    find_start_of_class_body,
    get_class_nodes,
    get_method_nodes,
    is_blank,
)
from .utils.file import read_file

FunctionsByName = dict[str, list[Function]]


def step_down_sort(python_file_path: str | Path) -> Optional[str]:
    source = read_file(python_file_path)
    syntax_tree = parse(source, filename=python_file_path)
    source_lines = source.splitlines()

    # First, sort top-level functions
    modified_lines = _sort_top_level_functions(source_lines, syntax_tree)

    # Re-parse to get updated line numbers for class sorting
    modified_source = "\n".join(modified_lines) + "\n"
    modified_tree = parse(modified_source)

    # Then, sort methods within classes
    final_lines: list[str] = []
    for cls in get_class_nodes(modified_tree):
        # Copy everything, which hasn't been copied so far, up until the class body,
        class_body_start = find_start_of_class_body(cls, modified_lines)
        final_lines.extend(modified_lines[len(final_lines) : class_body_start])

        # Copy class after sorting its methods
        final_lines.extend(_sort_methods_within_class(modified_lines, cls))

    # Copy remainder of file
    final_lines.extend(modified_lines[len(final_lines) :])

    if source_lines != final_lines:
        return normalize_blank_lines(final_lines)
    else:
        return None


def _sort_top_level_functions(source_lines: list[str], syntax_tree: Module) -> list[str]:
    """Sort top-level functions according to step-down rule."""
    func_dict = _find_top_level_functions(syntax_tree)

    if not func_dict:
        return source_lines

    # Barriers (module-level code that calls functions) divide the file into zones.
    # Functions within each zone are sorted independently, ensuring that functions
    # called at module level remain defined before the barrier that calls them.
    barrier_line_numbers = sorted(line_no for line_no, _ in _find_barriers(syntax_tree, func_dict))

    sorted_dict: FunctionsByName = {}
    for zone_funcs in _group_by_zone(func_dict, source_lines, barrier_line_numbers):
        deps = _find_dependencies(zone_funcs, _function_call_target)
        zone_sorted: FunctionsByName = {}
        for name in zone_funcs:
            _depth_first_sort(name, zone_funcs, deps, zone_sorted, [])
        sorted_dict.update(zone_sorted)

    return _rearrange_lines(source_lines, func_dict, sorted_dict)


def _find_top_level_functions(syntax_tree: Module) -> FunctionsByName:
    functions = defaultdict[str, list[Function]](list)
    for node in syntax_tree.body:
        if isinstance(node, (FunctionDef, AsyncFunctionDef)):
            functions[node.name].append(node)
    return functions


def _find_barriers(syntax_tree: Module, functions: FunctionsByName) -> list[tuple[int, set[str]]]:
    """Find module-level statements that call functions directly.

    Returns a list of (line_number, set of function names called) for each barrier.
    A barrier is any non-function-def statement that invokes a function.
    """
    barriers: list[tuple[int, set[str]]] = []
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
    func_dict: FunctionsByName, source_lines: list[str], barrier_line_numbers: list[int]
) -> Iterable[FunctionsByName]:
    """Group functions into zones separated by barrier lines.

    Each zone contains the functions that appear between two consecutive barriers
    (or before the first / after the last). Functions within a zone can be freely
    reordered without crossing a barrier.
    """
    zones: list[FunctionsByName] = [{} for _ in range(len(barrier_line_numbers) + 1)]
    for name, func in func_dict.items():
        func_start = determine_line_range(func[0], source_lines)[0]
        # barrier_lines are 1-based (AST), func_start is 0-based — the off-by-one
        # means `<` is the correct comparison (a function at 0-based line N is before
        # a barrier at 1-based line N+1).
        zone_idx = next(
            (i for i, bl in enumerate(barrier_line_numbers) if func_start < bl), len(barrier_line_numbers)
        )
        zones[zone_idx][name] = func
    return [z for z in zones if z]


def _sort_methods_within_class(source_lines: list[str], class_def: ClassDef) -> list[str]:
    # TODO: recursively sort methods within nested classes?

    # Find methods
    method_dict = defaultdict[str, list[Function]](list)
    for node in get_method_nodes(class_def):
        method_dict[node.name].append(node)

    # Build dependency graph among methods
    dependencies = _find_dependencies(method_dict, _method_call_target)

    # Re-order methods as needed
    sorted_dict: FunctionsByName = {}
    for method_name in method_dict:
        _depth_first_sort(method_name, method_dict, dependencies, sorted_dict, [])

    # Copy lines from the original source, shifting the methods around as needed
    return _rearrange_lines(
        source_lines, method_dict, sorted_dict, start=find_start_of_class_body(class_def, source_lines)
    )


def _rearrange_lines(
    source_lines: list[str], func_dict: FunctionsByName, sorted_dict: FunctionsByName, start: int = 0
) -> list[str]:
    original_nodes = list(chain(*func_dict.values()))
    sorted_nodes = list(chain(*sorted_dict.values()))

    def lines_of(node: Function) -> list[str]:
        start, stop = determine_line_range(node, source_lines)
        return source_lines[start:stop]

    result: list[str] = []
    pos = start
    sort_idx = 0

    for orig_node in original_nodes:
        orig_start, orig_stop = determine_line_range(orig_node, source_lines)
        result.extend(source_lines[pos:orig_start])  # filler is always emitted in original order
        pos = orig_stop

        if sort_idx >= len(sorted_nodes) or orig_node != sorted_nodes[sort_idx]:
            # The next sorted function hasn't reached its trigger slot yet; skip this slot.
            # Functions emitted early by the while-loop below also land here.
            continue

        result.extend(lines_of(sorted_nodes[sort_idx]))
        sort_idx += 1

        # A function that originally appeared before this slot should follow it immediately,
        # because its own slot was already passed (and skipped) earlier in the walk.
        while (
            sort_idx < len(sorted_nodes)
            and determine_line_range(sorted_nodes[sort_idx], source_lines)[0] < orig_start
        ):
            result.extend(lines_of(sorted_nodes[sort_idx]))
            sort_idx += 1

    if start == 0:
        # Include trailing content if we are doing the whole file
        result.extend(source_lines[pos:])

    result = _ensure_number_of_leading_blank_lines_remains_unchanged(
        source_lines[start : start + len(result)], result
    )
    return result


def _ensure_number_of_leading_blank_lines_remains_unchanged(
    original_lines: list[str],
    rearranged_lines: list[str],
):
    assert len(original_lines) == len(rearranged_lines)
    num_leading_blanks_before = 0
    for _ in takewhile(is_blank, original_lines):
        num_leading_blanks_before += 1
    num_leading_blanks_after = 0
    for _ in takewhile(is_blank, rearranged_lines):
        num_leading_blanks_after += 1
    if num_leading_blanks_after > num_leading_blanks_before:
        # We have additional leading blanks.
        # Move them to the back and let the formatter take care of the rest.
        diff = num_leading_blanks_after - num_leading_blanks_before
        return list(rearranged_lines[diff:]) + [""] * diff
    return rearranged_lines


def _find_dependencies(
    funcs: FunctionsByName,
    get_call_target: Callable[[Call], Optional[str]],
) -> dict[str, list[str]]:
    """Find dependencies between functions/methods based on call patterns.

    Note: decorator_list is excluded from the walk. Decorator arguments are evaluated
    at definition time, so any functions they call must already be defined before the
    decorated function — treating them as step-down dependencies would invert that.
    """
    dependencies: dict[str, list[str]] = defaultdict(list)
    for func in chain(*funcs.values()):
        subtrees = [*func.body, func.args, *([] if func.returns is None else [func.returns])]
        for subtree in subtrees:
            for node in walk(subtree):
                if isinstance(node, Call):
                    target = get_call_target(node)
                    if (
                        target is not None
                        and target in funcs
                        and not any(_is_pytest_fixture(f) for f in funcs[target])
                        and target not in dependencies[func.name]
                    ):
                        dependencies[func.name].append(target)
    return dependencies


def _is_pytest_fixture(node: Function) -> bool:
    """Check if a function is decorated with @pytest.fixture."""
    for decorator in node.decorator_list:
        target = decorator.func if isinstance(decorator, Call) else decorator
        if isinstance(target, Name) and target.id == "fixture":
            return True
        if isinstance(target, Attribute) and target.attr == "fixture":
            return True
    return False


def _method_call_target(node: Call) -> Optional[str]:
    """Extract target name from self.method() calls."""
    return node.func.attr if isinstance(node.func, Attribute) else None


def _function_call_target(node: Call) -> Optional[str]:
    """Extract target name from direct function() calls."""
    return node.func.id if isinstance(node.func, Name) else None


def _depth_first_sort(
    current_method_name: str,
    method_dict: FunctionsByName,
    dependencies: dict[str, list[str]],
    sorted_dict: FunctionsByName,
    path: list[str],
):
    # If this is a root node, but we've already traversed it, return.
    # Otherwise the sorting will not be stable in the presence of circular deps.
    if len(path) == 0 and current_method_name in sorted_dict:
        return

    path.append(current_method_name)

    # Rely on the fact that dicts maintain insertion order as of Python 3.7
    method = sorted_dict.pop(current_method_name, method_dict[current_method_name])
    sorted_dict[current_method_name] = method
    for dependency in dependencies[current_method_name]:
        if dependency not in path:
            _depth_first_sort(dependency, method_dict, dependencies, sorted_dict, path)

    path.pop()
