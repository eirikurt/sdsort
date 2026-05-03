from abc import ABC, abstractmethod
from ast import AsyncFunctionDef, Attribute, Call, ClassDef, FunctionDef, Name, stmt, walk
from typing import Generator

from .utils.ast import (
    ClassOrFunction,
    Function,
    determine_line_range,
    get_method_nodes,
)


def block_for(node: stmt, source_lines: list[str]):
    if isinstance(node, (FunctionDef, AsyncFunctionDef)):
        return FunctionBlock(node, source_lines)
    elif isinstance(node, ClassDef):
        return ClassBlock(node, source_lines)
    return None


class Block(ABC):
    def __init__(self, node: ClassOrFunction, source_lines: list[str]):
        self._node = node
        self.start, self.end = determine_line_range(node, source_lines)

    @abstractmethod
    def find_calls(self) -> Generator[Call, None, None]:
        raise NotImplementedError

    @property
    def is_pytest_fixture(self) -> bool:
        for decorator in self._node.decorator_list:
            target = decorator.func if isinstance(decorator, Call) else decorator
            if isinstance(target, Name) and target.id == "fixture":
                return True
            if isinstance(target, Attribute) and target.attr == "fixture":
                return True
        return False

    @property
    def name(self):
        return self._node.name


class ClassBlock(Block):
    _node: ClassDef

    def __init__(self, node: ClassDef, source_lines: list[str]):
        super().__init__(node, source_lines)
        method_nodes = get_method_nodes(node)
        self._methods = [FunctionBlock(m, source_lines) for m in method_nodes]

    def find_calls(self) -> Generator[Call, None, None]:
        for method in self._methods:
            yield from method.find_calls()

    def is_subclass_of(self, other: "ClassBlock") -> bool:
        for base in self._node.bases:
            if isinstance(base, Name) and base.id == other.name:
                return True
            if isinstance(base, Attribute) and base.attr == other.name:
                return True
        return False


class FunctionBlock(Block):
    def __init__(self, node: Function, source_lines: list[str]):
        super().__init__(node, source_lines)

    def find_calls(self) -> Generator[Call, None, None]:
        root = self._node
        assert not isinstance(root, ClassDef)
        subtrees = [*root.body, root.args, *([] if root.returns is None else [root.returns])]
        for subtree in subtrees:
            for node in walk(subtree):
                if isinstance(node, Call):
                    yield node
