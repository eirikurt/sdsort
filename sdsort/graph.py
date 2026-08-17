from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Generic, TypeAlias, TypeVar

from .block import Block, FunctionBlock

if TYPE_CHECKING:
    from collections.abc import Iterator

B = TypeVar("B", bound=Block)


class AcyclicGraph(Generic[B]):
    def __init__(self) -> None:
        self._edges: defaultdict[B, list[B]] = defaultdict(list)

    def add_edge(self, *, _from: B, to: B) -> bool:
        if to in self._edges[_from]:
            return False
        if _from == to or self._is_reachable(_from, start=to):
            return False
        self._edges[_from].append(to)
        return True

    def _is_reachable(self, target: B, *, start: B) -> bool:
        visited = set[B]()
        stack = [start]
        while stack:
            node = stack.pop()
            if node == target:
                return True
            if node in visited:
                continue
            visited.add(node)
            stack.extend(self._edges[node])
        return False

    def into_visitor(self) -> DependenciesVisitor[B]:
        return DependenciesVisitor(self._edges)


@dataclass(slots=True)
class DependenciesVisitor(Generic[B]):
    dependencies: dict[B, list[B]]
    sorted_blocks: list[B] = field(default_factory=list, init=False)
    path: list[B] = field(default_factory=list, init=False)

    def sort_top_block(self, block: B) -> None:
        self._move_current_block(block)
        for dependency in self._successors(block):
            self.sort_top_block(dependency)

    def sort(self, block: B) -> None:
        self.path.append(block)
        self._move_current_block(block)
        filtered = (s for s in self._successors(block) if s not in self.path)
        for dependency in filtered:
            self.sort(dependency)
        self.path.pop()

    def sort_by_partition(self: FnVisitor, block: FunctionBlock) -> None:
        self.path.append(block)
        self._move_current_block(block)
        filtered = (s for s in self._successors(block) if s not in self.path and s.key == block.key)
        for dependency in filtered:
            self.sort_by_partition(dependency)
        self.path.pop()

    def sort_by_partition_and_name(self: FnVisitor, block: FunctionBlock, seen: set[FunctionBlock]) -> None:
        if block in seen:
            return
        else:
            seen.add(block)
            self.path.append(block)
            self._move_current_block(block)
            filtered = (
                s for s in self._successors(block) if s not in self.path and s.key == block.key and s not in seen
            )
            for dependency in filtered:
                self.sort_by_partition_and_name(dependency, seen)
            self.path.pop()

    def _successors(self, block: B) -> Iterator[B]:
        return iter(self.dependencies[block])

    def _move_current_block(self, block: B) -> None:
        # Move the current block last
        try:
            self.sorted_blocks.remove(block)
        except ValueError:
            pass
        self.sorted_blocks.append(block)


FnVisitor: TypeAlias = DependenciesVisitor[FunctionBlock]
