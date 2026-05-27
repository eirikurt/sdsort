from abc import ABC, abstractmethod
from ast import AST, AsyncFunctionDef, Attribute, Call, ClassDef, Constant, FunctionDef, Name, stmt, walk
from typing import Generator, override

from .utils.ast import (
    Function,
    get_method_nodes,
)


def block_for(node: stmt, source_lines: list[str]):
    if isinstance(node, (FunctionDef, AsyncFunctionDef)):
        return FunctionBlock(node, source_lines)
    elif isinstance(node, ClassDef):
        return ClassBlock(node, source_lines)
    return StatementBlock(node, source_lines)


class Block(ABC):
    def __init__(self, node: AST, source_lines: list[str]):
        self._nodes = [node]

    @abstractmethod
    def append(self, node: AST) -> bool:
        raise NotImplementedError

    # XXX: rename to find_successors?
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
    @override
    def append(self, node: AST) -> bool:
        if not isinstance(node, (ClassDef, FunctionDef, AsyncFunctionDef)):
            self._nodes.append(node)
            return True
        return False

    @override
    def find_predecessors(self) -> Generator[str, None, None]:
        for node in self._nodes:
            for child in walk(node):
                if isinstance(child, Call) and isinstance(child.func, Name):
                    yield child.func.id

    @override
    def find_calls(self) -> Generator[Call, None, None]:
        yield from []


class ClassBlock(Block):
    _nodes: list[ClassDef]

    def __init__(self, node: ClassDef, source_lines: list[str]):
        super().__init__(node, source_lines)
        method_nodes = get_method_nodes(node)
        self._methods = [FunctionBlock(m, source_lines) for m in method_nodes]

    @override
    def append(self, node: AST) -> bool:
        return False

    @override
    def find_calls(self) -> Generator[Call, None, None]:
        for method in self._methods:
            yield from method.find_calls()

    @override
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


class FunctionBlock(Block):
    _nodes: list[Function]

    def __init__(self, node: Function, source_lines: list[str]):
        super().__init__(node, source_lines)

    @override
    def append(self, node: AST) -> bool:
        if isinstance(node, (FunctionDef, AsyncFunctionDef)) and node.name == self._nodes[0].name:
            self._nodes.append(node)
            return True
        return False

    @override
    def find_calls(self) -> Generator[Call, None, None]:
        for root in self._nodes:
            subtrees = [*root.body, root.args, *([] if root.returns is None else [root.returns])]
            for subtree in subtrees:
                for node in walk(subtree):
                    if isinstance(node, Call):
                        yield node

    @override
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

    @override
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
