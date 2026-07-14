from abc import ABC, abstractmethod
from ast import (
    AST,
    AnnAssign,
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
    Store,
    stmt,
    walk,
)
from collections.abc import Collection
from typing import Generator, Union

from .context import Context
from .utils.ast import (
    Function,
    determine_line_range,
    find_first_line,
    get_method_nodes,
)


def block_for(node: stmt, source_lines: list[str], context: Context):
    if isinstance(node, (FunctionDef, AsyncFunctionDef)):
        return FunctionBlock(node, source_lines, context)
    elif isinstance(node, ClassDef):
        return ClassBlock(node, source_lines, context)
    elif isinstance(node, (Import, ImportFrom)):
        return ImportBlock(node, source_lines, context)
    return StatementBlock(node, source_lines, context)


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

    def __init__(self, node: Union[Import, ImportFrom], source_lines: list[str], context: Context):
        super().__init__(node, context)
        self.start = find_first_line(node, source_lines)
        self.end = node.end_lineno or node.lineno

    def append(self, node: AST) -> bool:
        if isinstance(node, (Import, ImportFrom)):
            self._nodes.append(node)
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

    def __init__(self, node: stmt, source_lines: list[str], context: Context):
        super().__init__(node, context)
        self.start = find_first_line(node, source_lines)
        self.end = node.end_lineno or node.lineno
        self._names = set(self._extract_names(node))

    def append(self, node: AST) -> bool:
        if isinstance(node, stmt) and not isinstance(
            node, (ClassDef, FunctionDef, AsyncFunctionDef, Import, ImportFrom)
        ):
            self._nodes.append(node)
            self.end = max(self.end, node.end_lineno or node.lineno)
            self._names.update(self._extract_names(node))
            return True
        return False

    def _extract_names(self, node: AST):
        for child in walk(node):
            if isinstance(child, Assign):
                for target in child.targets:
                    if isinstance(target, Name):
                        yield target.id
            if isinstance(child, AnnAssign):
                if isinstance(child.target, Name):
                    yield child.target.id

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
        resolve_overlapping_ranges(self._methods)

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

        # A class-attribute assignment target (e.g. `config` in `config: dict = ...`) is
        # class-local, not a reference to a top-level definition, so it must not be treated
        # as a predecessor. Names being *read* (annotations, right-hand sides) still count,
        # even when they happen to share the target's name (e.g. `x = staticmethod(x)`).
        for statement in self._nodes[0].body:
            if isinstance(statement, (FunctionDef, AsyncFunctionDef)):
                continue
            for subtree in self._reference_subtrees(statement):
                for node in walk(subtree):
                    if isinstance(node, Name) and not isinstance(node.ctx, Store):
                        yield node.id

        for method in self._methods:
            yield from method.find_predecessors()

    def _reference_subtrees(self, statement: stmt) -> Generator[AST, None, None]:
        # Don't consider type annotations as predecessors when their evaluation is deferred
        if isinstance(statement, AnnAssign) and self._context.deferred_annotations:
            if statement.value is not None:
                yield statement.value
            return
        yield statement

    @property
    def names(self):
        return [n.name for n in self._nodes]

    @property
    def method_blocks(self) -> Collection[Block]:
        return self._methods


def resolve_overlapping_ranges(blocks: "Collection[Block]") -> None:
    """Clamp block starts so consecutive line ranges never overlap.

    `find_first_line` (which absorbs leading comments) and `find_last_line` (which
    absorbs trailing indented content) can both claim the same boundary line — e.g. an
    indented comment sitting between two adjacent defs with no blank line separating
    them. Overlapping ranges would make `_rearrange_lines` emit that line twice. Give any
    disputed line to the earlier block by advancing the later block's start.
    """
    running_end = 0
    for block in blocks:
        block.start = max(block.start, running_end)
        running_end = max(running_end, block.end)


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

        # XXX: it is not safe to omit annotations if the function has a decorator (e.g. @inject)
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
