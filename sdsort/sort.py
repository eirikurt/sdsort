from __future__ import annotations

from ast import Attribute, Call, ClassDef, Module, Name, parse
from collections import defaultdict
from dataclasses import dataclass, field
from io import BytesIO
from itertools import takewhile
from pathlib import Path
from tokenize import COMMENT, tokenize
from typing import TYPE_CHECKING, Generic, Literal, TypeAlias, TypeVar

from .block import Block, ClassBlock, FunctionBlock, block_for, resolve_overlapping_ranges
from .context import Context, gather_context
from .format import normalize_blank_lines
from .graph import AcyclicGraph
from .utils.ast import (
    find_start_of_class_body,
    get_class_nodes,
    is_blank,
)
from .utils.file import read_file, split_lines

if TYPE_CHECKING:
    from collections.abc import Callable, Collection

ResultType: TypeAlias = (
    tuple[Literal["sorted"], str] | tuple[Literal["skipped"], None] | tuple[Literal["unchanged"], None]
)


B = TypeVar("B", bound=Block)


def step_down_sort(python_file_path: str | Path) -> ResultType:
    source = read_file(python_file_path)
    if _should_skip(source):
        return ("skipped", None)

    syntax_tree = parse(source, filename=python_file_path)
    context = gather_context(syntax_tree, Path(python_file_path).resolve())
    source_lines = split_lines(source)

    # First, sort top-level blocks (functions and classes)
    modified_lines = _sort_top_level_blocks(source_lines, syntax_tree, context)

    if modified_lines == source_lines:
        # Nothing moved, so every line number still holds and the original tree remains valid.
        modified_tree = syntax_tree
    else:
        # Re-parse to get updated line numbers for class sorting
        modified_tree = parse("\n".join(modified_lines) + "\n")

    # Then, sort methods within classes
    final_lines: list[str] = []
    for cls in get_class_nodes(modified_tree):
        # Copy everything, which hasn't been copied so far, up until the class body,
        class_body_start = find_start_of_class_body(cls, modified_lines)
        final_lines.extend(modified_lines[len(final_lines) : class_body_start])

        # Copy class after sorting its methods
        final_lines.extend(_sort_methods_within_class(modified_lines, cls, context))

    # Copy remainder of file
    final_lines.extend(modified_lines[len(final_lines) :])

    if source_lines != final_lines:
        return ("sorted", normalize_blank_lines(final_lines))
    else:
        return ("unchanged", None)


def _should_skip(source: str) -> bool:
    # Tokenizing is expensive, so first do a cheap test
    if "sdsort" not in source:
        return False

    code_bytes = BytesIO(source.encode("utf-8"))
    for token in tokenize(code_bytes.readline):
        if token.type == COMMENT:
            key, _, value = token.string.lstrip("#").partition(":")
            if key.strip() == "sdsort" and value.strip() == "skip_file":
                return True
    return False


def _sort_top_level_blocks(source_lines: list[str], syntax_tree: Module, context: Context) -> list[str]:
    """Sort top-level functions/classes according to step-down rule."""
    blocks = _find_top_level_blocks(syntax_tree, source_lines, context)

    if not blocks:
        return source_lines

    deps = _find_dependencies(blocks, _function_call_target)
    visitor = DepthFirstVisitor(deps, [])
    for block in blocks:
        visitor.sort_top_block(block)
    return _rearrange_lines(source_lines, blocks, visitor.sorted_blocks)


def _find_top_level_blocks(syntax_tree: Module, source_lines: list[str], context: Context):
    blocks: list[Block] = []
    current_block: Block | None = None
    for node in syntax_tree.body:
        if current_block is None or not current_block.append(node):
            current_block = block_for(node, source_lines, context)
            blocks.append(current_block)

    resolve_overlapping_ranges(blocks)
    return blocks


def _sort_methods_within_class(source_lines: list[str], class_def: ClassDef, context: Context) -> list[str]:
    # TODO: recursively sort methods within nested classes?

    # Find methods
    class_block = ClassBlock(class_def, source_lines, context)
    blocks = tuple(class_block.method_blocks)

    # Build dependency graph among methods
    dependencies = _find_dependencies(blocks, _method_call_target)

    # Re-order methods as needed
    sorted_blocks: list[Block] = []
    match context.sort_by_visibility, context.sort_by_name:
        case False, _:
            visitor = DepthFirstVisitor(dependencies, sorted_blocks)
            for block in blocks:
                visitor.sort(block)
            # Copy lines from the original source, shifting the methods around as needed
            return _rearrange_lines(
                source_lines, blocks, sorted_blocks, find_start_of_class_body(class_def, source_lines)
            )
        case True, False:
            visitor = DepthFirstVisitor(dependencies, sorted_blocks)
            for method in sorted(blocks, key=lambda method: method.rank):
                visitor.sort_by_partition(method, method.rank)
            return _rearrange_lines(
                source_lines, blocks, sorted_blocks, find_start_of_class_body(class_def, source_lines)
            )
        case True, True:
            seen = set[FunctionBlock]()
            visitor = DepthFirstVisitor(dependencies, sorted_blocks)
            for method in sorted(blocks, key=lambda method: (method.rank, method.name)):
                visitor.sort_by_partition_and_name(method, method.rank, seen)
            return _rearrange_lines_by_partition(
                source_lines, blocks, sorted_blocks, find_start_of_class_body(class_def, source_lines)
            )


def _find_dependencies(
    blocks: Collection[B],
    get_call_target: Callable[[Call], str | None],
) -> AcyclicGraph[B]:
    dependencies = AcyclicGraph[B]()

    blocks_by_name: dict[str, list[B]] = defaultdict(list)
    for block in blocks:
        for name in block.names:
            blocks_by_name[name].append(block)

    for block in blocks:
        for name in block.find_predecessors():
            # XXX: filter out built-ins (e.g. str, int)?
            for predecessor_block in blocks_by_name.get(name, []):
                dependencies.add_edge(_from=predecessor_block, to=block)

    for block in blocks:
        for call in block.find_calls():
            target = get_call_target(call)
            if target is not None:
                for successor_block in blocks_by_name.get(target, []):
                    if isinstance(successor_block, FunctionBlock) and not successor_block.is_pytest_fixture:
                        dependencies.add_edge(_from=block, to=successor_block)

    return dependencies


@dataclass(slots=True)
class DepthFirstVisitor(Generic[B]):
    dependencies: AcyclicGraph[B]
    sorted_blocks: list[Block]
    path: list[Block] = field(default_factory=list, init=False)

    def sort_top_block(self, block: B) -> None:
        self._move_current_block(block)
        for dependency in self._iter_successors_if(lambda s: s not in self.path, block):
            self.sort_top_block(dependency)

    def sort(self, block: B) -> None:
        self.path.append(block)
        self._move_current_block(block)
        for dependency in self._iter_successors_if(lambda s: s not in self.path, block):
            self.sort(dependency)
        self.path.pop()

    def sort_by_partition(self: FnVisitor, block: FunctionBlock, rank: int) -> None:
        self.path.append(block)
        self._move_current_block(block)
        for dependency in self._iter_successors_if(lambda s: s not in self.path and s.rank == rank, block):
            self.sort_by_partition(dependency, rank)
        self.path.pop()

    def sort_by_partition_and_name(
        self: FnVisitor, block: FunctionBlock, rank: int, seen: set[FunctionBlock]
    ) -> None:
        if block in seen:
            return
        seen.add(block)
        self.path.append(block)
        self._move_current_block(block)
        for dependency in self._iter_successors_if(
            lambda s: s not in self.path and s.rank == rank and s not in seen, block
        ):
            self.sort_by_partition_and_name(dependency, rank, seen)
        self.path.pop()

    def _iter_successors_if(self, fn: Callable[[B], object], block: B) -> filter[B]:
        return filter(fn, self.dependencies.get_successors(block))

    def _move_current_block(self, block: Block) -> None:
        # Move the current block last
        try:
            self.sorted_blocks.remove(block)
        except ValueError:
            pass
        self.sorted_blocks.append(block)


FnVisitor: TypeAlias = DepthFirstVisitor[FunctionBlock]


def _rearrange_lines(
    source_lines: list[str], original_blocks: Collection[Block], sorted_blocks: list[Block], start: int = 0
) -> list[str]:
    def lines_of(block: Block) -> list[str]:
        return source_lines[block.start : block.end]

    result: list[str] = []
    pos = start
    sort_idx = 0

    for orig_block in original_blocks:
        result.extend(source_lines[pos : orig_block.start])  # filler is always emitted in original order
        pos = orig_block.end

        if sort_idx >= len(sorted_blocks) or orig_block != sorted_blocks[sort_idx]:
            # The next sorted block hasn't reached its trigger slot yet; skip this slot.
            # Blocks emitted early by the while-loop below also land here.
            continue

        result.extend(lines_of(sorted_blocks[sort_idx]))
        sort_idx += 1

        # A block that originally appeared before this slot should follow it immediately,
        # because its own slot was already passed (and skipped) earlier in the walk.
        while sort_idx < len(sorted_blocks) and sorted_blocks[sort_idx].start < orig_block.start:
            result.extend(lines_of(sorted_blocks[sort_idx]))
            sort_idx += 1
    return _finalize_rearranged_lines(source_lines, result, start, pos)


def _rearrange_lines_by_partition(
    source_lines: list[str], original_blocks: Collection[Block], sorted_blocks: list[Block], start: int = 0
) -> list[str]:
    def lines_of(block: Block) -> list[str]:
        return source_lines[block.start : block.end]

    result: list[str] = []
    pos = start
    sort_idx = 0
    blocks_by_start: dict[int, Block] = {}
    stop = start
    for block in original_blocks:
        blocks_by_start[block.start] = block
        stop = max(stop, block.end)
    while pos < stop:
        block = blocks_by_start.get(pos)
        if block is None:
            result.append(source_lines[pos])
            pos += 1
            continue
        result.extend(lines_of(sorted_blocks[sort_idx]))
        sort_idx += 1
        pos = block.end
    return _finalize_rearranged_lines(source_lines, result, start, pos)


def _finalize_rearranged_lines(source_lines: list[str], result: list[str], start: int, pos: int) -> list[str]:
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


def _method_call_target(node: Call) -> str | None:
    """Extract target name from self.method() calls."""
    return (
        node.func.attr
        if isinstance(node.func, Attribute) and isinstance(node.func.value, Name) and node.func.value.id == "self"
        else None
    )


def _function_call_target(node: Call) -> str | None:
    """Extract target name from direct function() calls."""
    return node.func.id if isinstance(node.func, Name) else None
