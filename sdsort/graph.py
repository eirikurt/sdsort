from collections import defaultdict

from .block import Block


class AcyclicGraph:
    def __init__(self) -> None:
        self._edges = defaultdict[Block, list[Block]](list)

    def add_edge(self, *, _from: Block, to: Block) -> bool:
        if to in self._edges[_from]:
            return False
        if _from == to or self._is_reachable(_from, start=to):
            return False
        self._edges[_from].append(to)
        return True

    def _is_reachable(self, target: Block, *, start: Block) -> bool:
        visited: set[Block] = set()
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

    def get_successors(self, _from: Block):
        yield from self._edges[_from]
