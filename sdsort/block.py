from abc import ABC, abstractmethod
from ast import (
    AST,
    Assign,
    AsyncFunctionDef,
    Attribute,
    Call,
    ClassDef,
    Constant,
    FunctionDef,
    Import,
    ImportFrom,
    Name,
    stmt,
    walk,
)
from collections.abc import Collection
from typing import Generator, Union

from .context import Context
from .utils.ast import (
    Function,
    determine_line_range,
    get_method_nodes,
)


def block_for(node: stmt, source_lines: list[str], context: Context):
    if isinstance(node, (FunctionDef, AsyncFunctionDef)):
        return FunctionBlock(node, source_lines, context)
    elif isinstance(node, ClassDef):
        return ClassBlock(node, source_lines, context)
    elif isinstance(node, (Import, ImportFrom)):
        return ImportBlock(node, context)
    return StatementBlock(node, context)


class Block(ABC):
    def __init__(self, node: AST, context: Context):
        self._nodes = [node]
        self._context = context
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

    @property
    @abstractmethod
    def names(self) -> Collection[str]:
        raise NotImplementedError


class ImportBlock(Block):
    _nodes: list[Union[Import, ImportFrom]]

    def __init__(self, node: Union[Import, ImportFrom], context: Context):
        super().__init__(node, context)
        # TODO: extend to capture leading comments
        self.start = node.lineno - 1
        self.end = node.end_lineno or node.lineno

    def append(self, node: AST) -> bool:
        if isinstance(node, (Import, ImportFrom)):
            self._nodes.append(node)
            self.start = min(self.start, node.lineno - 1)
            self.end = max(self.end, node.end_lineno or node.lineno)
            return True
        return False

    def find_predecessors(self) -> Generator[str, None, None]:
        yield from []

    def find_calls(self) -> Generator[Call, None, None]:
        yield from []

    @property
    def names(self) -> Collection[str]:
        return []


class StatementBlock(Block):
    _nodes: list[stmt]
    _names: set[str]

    def __init__(self, node: stmt, context: Context):
        super().__init__(node, context)
        # TODO: extend to capture leading comments
        self.start = node.lineno - 1
        self.end = node.end_lineno or node.lineno
        self._names = set(self._extract_names(node))

    def append(self, node: AST) -> bool:
        if isinstance(node, stmt) and not isinstance(
            node, (ClassDef, FunctionDef, AsyncFunctionDef, Import, ImportFrom)
        ):
            self._nodes.append(node)
            self.start = min(self.start, node.lineno - 1)
            self.end = max(self.end, node.end_lineno or node.lineno)
            self._names.update(self._extract_names(node))
            return True
        return False

    def _extract_names(self, node: AST):
        if isinstance(node, Assign):
            for target in node.targets:
                if isinstance(target, Name):
                    yield target.id

    def find_predecessors(self) -> Generator[str, None, None]:
        for node in self._nodes:
            for child in walk(node):
                if isinstance(child, Name) and child.id not in self._names:
                    yield child.id

    def find_calls(self) -> Generator[Call, None, None]:
        yield from []

    @property
    def names(self) -> Collection[str]:
        return self._names


class ClassBlock(Block):
    _nodes: list[ClassDef]

    def __init__(self, node: ClassDef, source_lines: list[str], context: Context):
        super().__init__(node, context)
        self.start, self.end = determine_line_range(node, source_lines)
        method_nodes = get_method_nodes(node)
        self._methods: list[FunctionBlock] = []
        current_block: Union[Block, None] = None
        for method_node in method_nodes:
            if current_block is None or not current_block.append(method_node):
                current_block = FunctionBlock(method_node, source_lines, self._context)
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

        # XXX: this should probably be narrowed to only consider type hints and names on the right hand side of assignments
        for statement in self._nodes[0].body:
            if not isinstance(statement, (FunctionDef, AsyncFunctionDef)):
                for node in walk(statement):
                    if isinstance(node, Name):
                        yield node.id

        for method in self._methods:
            yield from method.find_predecessors()

    @property
    def names(self):
        return [n.name for n in self._nodes]

    @property
    def method_blocks(self) -> Collection[Block]:
        return self._methods


class FunctionBlock(Block):
    _nodes: list[Function]

    def __init__(self, node: Function, source_lines: list[str], context: Context):
        super().__init__(node, context)
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
        for function in self._nodes:
            for decorator in function.decorator_list:
                for node in walk(decorator):
                    if isinstance(node, Name):
                        yield node.id

        if not self._context.deferred_annotations:
            yield from self._get_type_annotations()

    def _get_type_annotations(self):
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
    def names(self):
        return [n.name for n in self._nodes]
