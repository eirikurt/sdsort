from ast import Attribute, Call, ClassDef, Module, Name, parse
from collections import defaultdict
from itertools import chain, takewhile
from pathlib import Path
from typing import Callable, Optional, Union

from .block import Block, ClassBlock, FunctionBlock, block_for
from .format import normalize_blank_lines
from .graph import AcyclicGraph
from .utils.ast import (
    find_start_of_class_body,
    get_class_nodes,
    get_method_nodes,
    is_blank,
)
from .utils.file import read_file

BlocksByName = dict[str, list[Block]]


def step_down_sort(python_file_path: str | Path) -> Optional[str]:
    # New algorithm
    # Segment source code into blocks (classes, functions, other)
    # Find hard dependencies, which if not honored will result in syntax errors
    # Find call dependencies, which we aspire to sort by, but only if it doesn't violate hard dependencies
    #   Idea: only add call deps if it doesn't result in a circle in the dep graph
    # Order the blocks via traversal of the dep tree/forest
    # Re-arrange code

    source = read_file(python_file_path)
    syntax_tree = parse(source, filename=python_file_path)
    source_lines = source.splitlines()

    # First, sort top-level functions
    modified_lines = _sort_top_level_blocks(source_lines, syntax_tree)

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


def _sort_top_level_blocks(source_lines: list[str], syntax_tree: Module) -> list[str]:
    """Sort top-level functions/classes according to step-down rule."""
    blocks = _find_top_level_blocks(syntax_tree, source_lines)

    if not blocks:
        return source_lines

    deps = _find_dependencies(blocks)
    sorted_blocks: list[Block] = []
    for block in blocks:
        _depth_first_sort(block, blocks, deps, sorted_blocks, [])
    return _rearrange_lines(source_lines, blocks, sorted_blocks)


def _find_top_level_blocks(syntax_tree: Module, source_lines: list[str]):
    blocks: list[Block] = []
    current_block: Union[Block, None] = None
    for node in syntax_tree.body:
        if current_block is None or not current_block.append(node):
            current_block = block_for(node, source_lines)
            blocks.append(current_block)
    return blocks


def _sort_methods_within_class(source_lines: list[str], class_def: ClassDef) -> list[str]:
    # TODO: recursively sort methods within nested classes?

    # Find methods
    method_dict = defaultdict[str, list[Block]](list)
    for node in get_method_nodes(class_def):
        block = FunctionBlock(node, source_lines)
        method_dict[block.name].append(block)

    # Build dependency graph among methods
    dependencies = _find_dependencies(method_dict, _method_call_target)

    # Re-order methods as needed
    sorted_dict: BlocksByName = {}
    for method_name in method_dict:
        _depth_first_sort(method_name, method_dict, dependencies, sorted_dict, [])

    # Copy lines from the original source, shifting the methods around as needed
    return _rearrange_lines(
        source_lines, method_dict, sorted_dict, start=find_start_of_class_body(class_def, source_lines)
    )


def _find_dependencies(
    blocks: list[Block],
    get_call_target: Callable[[Call], Optional[str]],
):
    dependencies = AcyclicGraph()
    blocks_by_name = {block.name: block for block in blocks if isinstance(block, (ClassBlock, FunctionBlock))}

    for block in blocks:
        for name in block.find_predecessors():
            predecessor_block = blocks_by_name.get(name)
            if predecessor_block is not None:
                dependencies.add_edge(_from=predecessor_block, to=block)

    for block in blocks:
        for call in block.find_calls():
            target = get_call_target(call)
            if target is not None:
                successor_block = blocks_by_name.get(target)
                if successor_block is not None and not successor_block.is_pytest_fixture:
                    dependencies.add_edge(_from=block, to=successor_block)

    return dependencies


def _find_subclasses(parent_class: ClassBlock, blocks_by_name: BlocksByName):
    for block in chain(*blocks_by_name.values()):
        if isinstance(block, ClassBlock) and block != parent_class:
            if block.is_subclass_of(parent_class):
                yield block


def _depth_first_sort(
    current_block_name: str,
    blocks_by_name: BlocksByName,
    dependencies: dict[str, list[str]],
    sorted_blocks: BlocksByName,
    path: list[str],
):
    # If this is a root node, but we've already traversed it, return.
    # Otherwise the sorting will not be stable in the presence of circular deps.
    if len(path) == 0 and current_block_name in sorted_blocks:
        return

    path.append(current_block_name)

    # Rely on the fact that dicts maintain insertion order as of Python 3.7
    block_list = sorted_blocks.pop(current_block_name, blocks_by_name[current_block_name])
    sorted_blocks[current_block_name] = block_list
    for dependency in dependencies[current_block_name]:
        if dependency not in path:
            _depth_first_sort(dependency, blocks_by_name, dependencies, sorted_blocks, path)

    path.pop()


def _rearrange_lines(
    source_lines: list[str], blocks_by_name: BlocksByName, sorted_blocks_by_name: BlocksByName, start: int = 0
) -> list[str]:
    original_blocks = list(chain(*blocks_by_name.values()))
    sorted_blocks = list(chain(*sorted_blocks_by_name.values()))

    def lines_of(block: Block) -> list[str]:
        return source_lines[block.start : block.end]

    result: list[str] = []
    pos = start
    sort_idx = 0

    for orig_block in original_blocks:
        result.extend(source_lines[pos : orig_block.start])  # filler is always emitted in original order
        pos = orig_block.end

        if sort_idx >= len(sorted_blocks) or orig_block != sorted_blocks[sort_idx]:
            # The next sorted function hasn't reached its trigger slot yet; skip this slot.
            # Functions emitted early by the while-loop below also land here.
            continue

        result.extend(lines_of(sorted_blocks[sort_idx]))
        sort_idx += 1

        # A function that originally appeared before this slot should follow it immediately,
        # because its own slot was already passed (and skipped) earlier in the walk.
        while sort_idx < len(sorted_blocks) and sorted_blocks[sort_idx].start < orig_block.start:
            result.extend(lines_of(sorted_blocks[sort_idx]))
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


def _method_call_target(node: Call) -> Optional[str]:
    """Extract target name from self.method() calls."""
    return node.func.attr if isinstance(node.func, Attribute) else None


def _function_call_target(node: Call) -> Optional[str]:
    """Extract target name from direct function() calls."""
    return node.func.id if isinstance(node.func, Name) else None
