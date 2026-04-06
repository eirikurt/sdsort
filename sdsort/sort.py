from ast import AsyncFunctionDef, Attribute, Call, ClassDef, FunctionDef, Module, Name, parse, walk
from collections import defaultdict
from typing import Callable, Iterable, Optional

from .format import normalize_blank_lines
from .utils.ast import Function, determine_line_range, get_class_nodes, get_method_nodes
from .utils.file import read_file


def step_down_sort(python_file_path: str) -> Optional[str]:
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
        # Copy everything, which hasn't been copied so far, up until the class def,
        final_lines.extend(modified_lines[len(final_lines) : cls.lineno])

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

    sorted_dict: dict[str, Function] = {}
    for zone_funcs in _group_by_zone(func_dict, source_lines, barrier_line_numbers):
        deps = _find_dependencies(zone_funcs, _function_call_target)
        zone_sorted: dict[str, Function] = {}
        for name in zone_funcs:
            _depth_first_sort(name, zone_funcs, deps, zone_sorted, [])
        sorted_dict.update(zone_sorted)

    return _rearrange_top_level_functions(source_lines, func_dict, sorted_dict)


def _find_top_level_functions(syntax_tree: Module) -> dict[str, Function]:
    return {node.name: node for node in syntax_tree.body if isinstance(node, (FunctionDef, AsyncFunctionDef))}


def _find_barriers(syntax_tree: Module, functions: dict[str, Function]) -> list[tuple[int, set[str]]]:
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
    func_dict: dict[str, Function], source_lines: list[str], barrier_line_numbers: list[int]
) -> Iterable[dict[str, Function]]:
    """Group functions into zones separated by barrier lines.

    Each zone contains the functions that appear between two consecutive barriers
    (or before the first / after the last). Functions within a zone can be freely
    reordered without crossing a barrier.
    """
    zones: list[dict[str, Function]] = [{} for _ in range(len(barrier_line_numbers) + 1)]
    for name, func in func_dict.items():
        func_start = determine_line_range(func, source_lines)[0]
        # barrier_lines are 1-based (AST), func_start is 0-based — the off-by-one
        # means `<` is the correct comparison (a function at 0-based line N is before
        # a barrier at 1-based line N+1).
        zone_idx = next(
            (i for i, bl in enumerate(barrier_line_numbers) if func_start < bl), len(barrier_line_numbers)
        )
        zones[zone_idx][name] = func
    return [z for z in zones if z]


def _rearrange_top_level_functions(
    source_lines: list[str],
    func_dict: dict[str, Function],
    sorted_dict: dict[str, Function],
) -> list[str]:
    # Pre-compute all line ranges up front.
    ranges = {name: determine_line_range(node, source_lines) for name, node in func_dict.items()}

    def lines_of(name: str) -> list[str]:
        start, stop = ranges[name]
        return source_lines[start : stop + 1]

    result: list[str] = []
    pos = 0
    sorted_names = list(sorted_dict.keys())
    sort_idx = 0

    for orig_name in func_dict:
        orig_start, orig_stop = ranges[orig_name]
        result.extend(source_lines[pos:orig_start])  # filler is always emitted in original order
        pos = orig_stop + 1

        if sort_idx >= len(sorted_names) or orig_name != sorted_names[sort_idx]:
            # The next sorted function hasn't reached its trigger slot yet; skip this slot.
            # Functions emitted early by the while-loop below also land here.
            continue

        result.extend(lines_of(sorted_names[sort_idx]))
        sort_idx += 1

        # A function that originally appeared before this slot should follow it immediately,
        # because its own slot was already passed (and skipped) earlier in the walk.
        while sort_idx < len(sorted_names) and ranges[sorted_names[sort_idx]][0] < orig_start:
            result.extend(lines_of(sorted_names[sort_idx]))
            sort_idx += 1

    result.extend(source_lines[pos:])  # trailing content
    return result


def _sort_methods_within_class(source_lines: list[str], class_def: ClassDef) -> list[str]:
    # TODO: recursively sort methods within nested classes?

    # Find methods
    method_dict = {node.name: node for node in get_method_nodes(class_def)}

    # Build dependency graph among methods
    dependencies = _find_dependencies(method_dict, _method_call_target)

    # Re-order methods as needed
    sorted_dict: dict[str, Function] = {}
    for method_name in method_dict:
        _depth_first_sort(method_name, method_dict, dependencies, sorted_dict, [])

    # Copy lines from the original source, shifting the methods around as needed
    return _rearrange_class_code(class_def, method_dict, sorted_dict, source_lines)


def _find_dependencies(
    funcs: dict[str, Function],
    get_call_target: Callable[[Call], Optional[str]],
) -> dict[str, list[str]]:
    """Find dependencies between functions/methods based on call patterns.

    Note: decorator_list is excluded from the walk. Decorator arguments are evaluated
    at definition time, so any functions they call must already be defined before the
    decorated function — treating them as step-down dependencies would invert that.
    """
    dependencies: dict[str, list[str]] = defaultdict(list)
    for func in funcs.values():
        subtrees = [*func.body, func.args, *([] if func.returns is None else [func.returns])]
        for subtree in subtrees:
            for node in walk(subtree):
                if isinstance(node, Call):
                    target = get_call_target(node)
                    if (
                        target is not None
                        and target in funcs
                        and not _is_pytest_fixture(funcs[target])
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
    method_dict: dict[str, Function],
    dependencies: dict[str, list[str]],
    sorted_dict: dict[str, Function],
    path: list[str],
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
    method_dict: dict[str, Function],
    sorted_dict: dict[str, Function],
    source_lines: list[str],
) -> list[str]:
    """Rearrange source lines by swapping functions from their original positions to sorted positions."""
    result: list[str] = []
    source_position = class_def.lineno
    for original, replacement in zip(method_dict.values(), sorted_dict.values()):
        original_range = determine_line_range(original, source_lines)
        replacement_range = determine_line_range(replacement, source_lines)
        result.extend(source_lines[source_position : original_range[0]])
        result.extend(source_lines[replacement_range[0] : replacement_range[1]])
        source_position = original_range[1]
    return result
