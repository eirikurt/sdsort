from abc import ABC, abstractmethod
from ast import AST, AsyncFunctionDef, Attribute, Call, ClassDef, Constant, FunctionDef, Name, stmt, walk
from collections.abc import Collection
from typing import Generator, Union

from .utils.ast import (
    Function,
    determine_line_range,
    get_method_nodes,
)


def block_for(node: stmt, source_lines: list[str]):
    if isinstance(node, (FunctionDef, AsyncFunctionDef)):
        return FunctionBlock(node, source_lines)
    elif isinstance(node, ClassDef):
        return ClassBlock(node, source_lines)
    return StatementBlock(node)


class Block(ABC):
    def __init__(self, node: AST):
        self._nodes = [node]
        self.start = -1
        self.end = -1

    @abstractmethod
    def append(self, node: AST) -> bool:
        raise NotImplementedError

    @abstractmethod
    def find_calls(self) -> Generator[Call, None, None]:
        raise NotImplementedError

    @abstractmethod
    def find_predecessors(self) -> Generator[str, None, None]:
        raise NotImplementedError

    @property
    def is_pytest_fixture(self) -> bool:
        return False


class StatementBlock(Block):
    _nodes: list[stmt]

    def __init__(self, node: stmt):
        super().__init__(node)
        self.start = node.lineno
        self.end = node.end_lineno or node.lineno

    def append(self, node: AST) -> bool:
        if isinstance(node, stmt) and not isinstance(node, (ClassDef, FunctionDef, AsyncFunctionDef)):
            self._nodes.append(node)
            self.start = min(self.start, node.lineno)
            self.end = max(self.end, node.end_lineno or node.lineno)
            return True
        return False

    def find_predecessors(self) -> Generator[str, None, None]:
        for node in self._nodes:
            for child in walk(node):
                if isinstance(child, Call) and isinstance(child.func, Name):
                    yield child.func.id

    def find_calls(self) -> Generator[Call, None, None]:
        yield from []


class ClassBlock(Block):
    _nodes: list[ClassDef]

    def __init__(self, node: ClassDef, source_lines: list[str]):
        super().__init__(node)
        self.start, self.end = determine_line_range(node, source_lines)
        method_nodes = get_method_nodes(node)
        current_block: Union[Block, None] = None
        self._methods: list[FunctionBlock] = []
        current_block: Union[Block, None] = None
        for method_node in method_nodes:
            if current_block is None or not current_block.append(method_node):
                current_block = FunctionBlock(method_node, source_lines)
                self._methods.append(current_block)

    def append(self, node: AST) -> bool:
        return False

    def find_calls(self) -> Generator[Call, None, None]:
        for method in self._methods:
            yield from method.find_calls()

    def find_predecessors(self) -> Generator[str, None, None]:
        for base in self._nodes[0].bases:
            for node in walk(base):
                if isinstance(node, Name):
                    yield node.id
                if isinstance(node, Attribute):
                    yield node.attr

        for method in self._methods:
            yield from method.find_predecessors()

    @property
    def name(self):
        return self._nodes[0].name

    @property
    def method_blocks(self) -> Collection[Block]:
        return self._methods


class FunctionBlock(Block):
    _nodes: list[Function]

    def __init__(self, node: Function, source_lines: list[str]):
        super().__init__(node)
        self.start, self.end = determine_line_range(node, source_lines)
        self._source_lines = source_lines

    def append(self, node: AST) -> bool:
        if isinstance(node, (FunctionDef, AsyncFunctionDef)) and node.name == self._nodes[0].name:
            self._nodes.append(node)
            start, end = determine_line_range(node, self._source_lines)
            self.start = min(self.start, start)
            self.end = max(self.end, end)
            return True
        return False

    def find_calls(self) -> Generator[Call, None, None]:
        for root in self._nodes:
            subtrees = [*root.body, root.args, *([] if root.returns is None else [root.returns])]
            for subtree in subtrees:
                for node in walk(subtree):
                    if isinstance(node, Call):
                        yield node

    def find_predecessors(self) -> Generator[str, None, None]:
        # Look for type hints in the function signature.
        # Prior to Python 3.14, names referenced in type hints must be declared first.
        # TODO: relax this for Python >=3.14
        for root in self._nodes:
            all_args = [*root.args.posonlyargs, *root.args.args, *root.args.kwonlyargs]
            if root.args.vararg:
                all_args.append(root.args.vararg)
            if root.args.kwarg:
                all_args.append(root.args.kwarg)
            annotation_nodes = [a.annotation for a in all_args if a.annotation is not None]
            if root.returns is not None:
                annotation_nodes.append(root.returns)
            for annotation in annotation_nodes:
                if isinstance(annotation, Constant) and isinstance(annotation.value, str):
                    continue  # skip lazy string annotations like "MyClass"
                for node in walk(annotation):
                    if isinstance(node, Name):
                        yield node.id

    @property
    def is_pytest_fixture(self) -> bool:
        node = self._nodes[0]
        assert isinstance(node, (FunctionDef, AsyncFunctionDef))
        for decorator in node.decorator_list:
            target = decorator.func if isinstance(decorator, Call) else decorator
            if isinstance(target, Name) and target.id == "fixture":
                return True
            if isinstance(target, Attribute) and target.attr == "fixture":
                return True
        return False

    @property
    def name(self):
        return self._nodes[0].name
