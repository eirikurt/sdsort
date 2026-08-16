from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Generic, TypeVar

from .block import Block

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

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

    def get_successors(self, _from: B) -> Generator[B, None, None]:
        yield from self._edges[_from]

    def iter_if(self, fn: Callable[[B], object], block: B) -> filter[B]:
        return filter(fn, self.get_successors(block))
