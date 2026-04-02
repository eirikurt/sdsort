import os
import time
from ast import AST, AsyncFunctionDef, Attribute, Call, ClassDef, FunctionDef, Module, Name, parse, walk
from collections import defaultdict
from dataclasses import dataclass
from glob import glob
from typing import Callable, Iterable, Optional, Protocol, TypeGuard, Union

import click

FunDef = Union[FunctionDef, AsyncFunctionDef]


@click.command()
@click.argument(
    "paths",
    nargs=-1,
    type=click.Path(exists=True, file_okay=True, dir_okay=True, readable=True),
    is_eager=True,
)
@click.option("--check", is_flag=True, help="Don't write changes, just report if files would be re-arranged.")
def main(paths: tuple[str, ...], check: bool):
    start_time = time.monotonic()
    file_paths = _expand_file_paths(paths)
    modified_files: list[str] = []
    pristine_files: list[str] = []

    for file_path in sorted(file_paths):
        modified_source = step_down_sort(file_path)
        if modified_source is not None:
            if not check:
                with open(file_path, "w") as file:
                    file.write(modified_source)
            modified_files.append(file_path)
        else:
            pristine_files.append(file_path)

    if len(modified_files) > 0:
        if check:
            click.secho("The following files would be re-arranged:", fg="yellow", bold=True)
        else:
            click.secho("Re-arranged the following files:", fg="yellow", bold=True)
        for modified_file in modified_files:
            click.echo(f"- {modified_file}")
    if len(pristine_files) > 0:
        click.secho(
            f"{len(pristine_files)} file{'' if len(pristine_files) == 1 else 's'} left unchanged", fg="green"
        )
    if len(modified_files) == 0 and len(pristine_files) == 0:
        click.secho("No python files found to format", fg="green")

    elapsed = time.monotonic() - start_time
    total_files = len(modified_files) + len(pristine_files)
    click.secho(f"Done! Checked {total_files} file{'' if total_files == 1 else 's'} in {elapsed:.2f}s", dim=True)

    if check and len(modified_files) > 0:
        raise SystemExit(1)


def _expand_file_paths(paths: tuple[str, ...]) -> Iterable[str]:
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
    final_lines: list[str] = []
    for cls in _find_classes(modified_tree):
        # Copy everything, which hasn't been copied so far, up until the class def,
        final_lines.extend(modified_lines[len(final_lines) : cls.lineno])

        # Copy class after sorting its methods
        final_lines.extend(_sort_methods_within_class(modified_lines, cls))

    # Copy remainder of file
    final_lines.extend(modified_lines[len(final_lines) :])

    if source_lines != final_lines:
        return _normalize_blank_lines(final_lines)
    else:
        return None


def _normalize_blank_lines(lines: list[str]) -> str:
    """Normalize blank lines per PEP 8:
    - 2 blank lines before top-level function/class definitions
    - 1 blank line between methods in a class (0 before the first)
    """
    # Collect 0-based line indices where PEP 8 spacing rules apply
    # Maps line_index -> required number of preceding blank lines
    required_blanks: dict[int, int] = {}
    tree = parse("\n".join(lines) + "\n")

    for node in tree.body:
        if isinstance(node, (FunctionDef, AsyncFunctionDef, ClassDef)):
            target = min((d.lineno for d in node.decorator_list), default=node.lineno)
            # Scan backwards past any leading comments so the 2 blank lines are
            # inserted before the comment block, not between the comment and the def.
            marker = target - 1  # 0-based index of the def/decorator line
            while marker > 0 and lines[marker - 1].strip().startswith("#"):
                marker -= 1
            required_blanks[marker] = 2

    for node in tree.body:
        if not isinstance(node, ClassDef):
            continue
        methods = [n for n in node.body if isinstance(n, (FunctionDef, AsyncFunctionDef))]
        for i, method in enumerate(methods):
            target = min((d.lineno for d in method.decorator_list), default=method.lineno)
            if i == 0:
                # For the first method, preserve existing blank lines (up to 1) rather
                # than forcing 0 — this allows a blank between class variables and the
                # first method when the author already wrote one.
                preceding_blanks = 0
                for line_idx in range(target - 2, -1, -1):
                    if lines[line_idx].strip() == "":
                        preceding_blanks += 1
                    else:
                        break
                required_blanks[target - 1] = min(preceding_blanks, 1)
            else:
                required_blanks[target - 1] = 1  # 0-based

    # Walk lines, stripping existing blank lines before def sites
    # and injecting the required number
    result: list[str] = []
    i = 0
    while i < len(lines):
        if i in required_blanks:
            # Strip any blank lines already accumulated at the end of result
            while result and result[-1].strip() == "":
                result.pop()
            # Inject the required blank lines
            result.extend([""] * required_blanks[i])
        line = lines[i]
        # Cap consecutive blank lines at 2 (PEP 8) for lines not controlled by required_blanks
        if (
            i not in required_blanks
            and line.strip() == ""
            and len(result) >= 2
            and result[-1].strip() == ""
            and result[-2].strip() == ""
        ):
            i += 1
            continue
        result.append(line)
        i += 1

    return "\n".join(result).strip() + "\n"


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


def _sort_top_level_functions(source_lines: list[str], syntax_tree: Module) -> list[str]:
    """Sort top-level functions according to step-down rule."""
    func_dict = _find_top_level_functions(syntax_tree)

    if not func_dict:
        return source_lines

    # Barriers (module-level code that calls functions) divide the file into zones.
    # Functions within each zone are sorted independently, ensuring that functions
    # called at module level remain defined before the barrier that calls them.
    barrier_line_numbers = sorted(line_no for line_no, _ in _find_barriers(syntax_tree, func_dict))

    sorted_dict: dict[str, FunDef] = {}
    for zone_funcs in _group_by_zone(func_dict, source_lines, barrier_line_numbers):
        deps = _find_dependencies(zone_funcs, _function_call_target)
        zone_sorted: dict[str, FunDef] = {}
        for name in zone_funcs:
            _depth_first_sort(name, zone_funcs, deps, zone_sorted, [])
        sorted_dict.update(zone_sorted)

    return _rearrange_top_level_functions(source_lines, func_dict, sorted_dict)


def _find_top_level_functions(syntax_tree: Module) -> dict[str, FunDef]:
    return {node.name: node for node in syntax_tree.body if isinstance(node, (FunctionDef, AsyncFunctionDef))}


def _find_barriers(syntax_tree: Module, functions: dict[str, FunDef]) -> list[tuple[int, set[str]]]:
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
    func_dict: dict[str, FunDef], source_lines: list[str], barrier_line_numbers: list[int]
) -> Iterable[dict[str, FunDef]]:
    """Group functions into zones separated by barrier lines.

    Each zone contains the functions that appear between two consecutive barriers
    (or before the first / after the last). Functions within a zone can be freely
    reordered without crossing a barrier.
    """
    zones: list[dict[str, FunDef]] = [{} for _ in range(len(barrier_line_numbers) + 1)]
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


@dataclass
class Segment:
    start: int
    stop: int

    @property
    def is_valid(self):
        return self.stop >= self.start


@dataclass
class FunctionSegment(Segment):
    name: str
    node: FunDef


def _rearrange_top_level_functions(
    source_lines: list[str],
    func_dict: dict[str, FunDef],
    sorted_dict: dict[str, FunDef],
) -> list[str]:
    function_ranges = [_determine_line_range(f, source_lines) for f in func_dict.values()]
    function_segments = {
        name: FunctionSegment(start=start, stop=stop, name=name, node=node)
        for ((name, node), (start, stop)) in zip(func_dict.items(), function_ranges)
    }
    all_segments: list[Segment] = []
    for fun_seg in function_segments.values():
        filler = Segment(start=0 if len(all_segments) == 0 else all_segments[-1].stop + 1, stop=fun_seg.start - 1)
        if filler.is_valid:
            all_segments.append(filler)
        all_segments.append(fun_seg)
    filler = Segment(start=all_segments[-1].stop + 1, stop=len(source_lines) - 1)
    if filler.is_valid:
        all_segments.append(filler)

    result: list[str] = []

    def append_segment(segment: Segment):
        result.extend(source_lines[segment.start : segment.stop + 1])

    sorted_function_stack = list(reversed(sorted_dict.keys()))
    for segment in all_segments:
        if isinstance(segment, FunctionSegment):
            if segment.name == sorted_function_stack[-1]:
                append_segment(segment)
                sorted_function_stack.pop()
                prev = segment
                while (
                    len(sorted_function_stack) > 0
                    and (past_segment := function_segments[sorted_function_stack[-1]]).start < prev.start
                ):
                    append_segment(past_segment)
                    sorted_function_stack.pop()
        else:
            append_segment(segment)

    return result


def _sort_methods_within_class(source_lines: list[str], class_def: ClassDef) -> list[str]:
    # TODO: recursively sort methods within nested classes?

    # Find methods
    method_dict = {node.name: node for node in class_def.body if isinstance(node, (FunctionDef, AsyncFunctionDef))}

    # Build dependency graph among methods
    dependencies = _find_dependencies(method_dict, _method_call_target)

    # Re-order methods as needed
    sorted_dict: dict[str, FunDef] = {}
    for method_name in method_dict:
        _depth_first_sort(method_name, method_dict, dependencies, sorted_dict, [])

    # Copy lines from the original source, shifting the methods around as needed
    return _rearrange_class_code(class_def, method_dict, sorted_dict, source_lines)


def _find_dependencies(
    funcs: dict[str, FunDef],
    get_call_target: Callable[[Call], Optional[str]],
) -> dict[str, list[str]]:
    """Find dependencies between functions/methods based on call patterns.

    Note: For top-level functions, decorators are not included as dependencies.
    Decorators must be defined before use (syntactic constraint), but for step-down
    ordering, the decorated function should come before its decorator.
    """
    dependencies: dict[str, list[str]] = defaultdict(list)
    for func in funcs.values():
        for node in walk(func):
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


def _is_pytest_fixture(node: FunDef) -> bool:
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
    method_dict: dict[str, FunDef],
    dependencies: dict[str, list[str]],
    sorted_dict: dict[str, FunDef],
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
    method_dict: dict[str, FunDef],
    sorted_dict: dict[str, FunDef],
    source_lines: list[str],
) -> list[str]:
    result, _ = _rearrange_functions(source_lines, method_dict, sorted_dict, start=class_def.lineno)
    return result


def _rearrange_functions(
    source_lines: list[str],
    func_dict: dict[str, FunDef],
    sorted_dict: dict[str, FunDef],
    start: int = 0,
) -> tuple[list[str], int]:
    """Rearrange source lines by swapping functions from their original positions to sorted positions."""
    result: list[str] = []
    source_position = start
    for original, replacement in zip(func_dict.values(), sorted_dict.values()):
        original_range = _determine_line_range(original, source_lines)
        replacement_range = _determine_line_range(replacement, source_lines)
        result.extend(source_lines[source_position : original_range[0]])
        result.extend(source_lines[replacement_range[0] : replacement_range[1]])
        source_position = original_range[1]
    return result, source_position


def _determine_line_range(method: FunDef, source_lines: list[str]) -> tuple[int, int]:
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

    # Include leading whitespace, at least up to a point?
    # peek = source_lines[start - 1] if start > 0 else "nope"
    # while len(peek.strip()) == 0:
    #    start -= 1
    #    peek = source_lines[start - 1] if start > 0 else "nope"

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
