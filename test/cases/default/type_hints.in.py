from ast import AST, AsyncFunctionDef, ClassDef, FunctionDef, walk
from typing import Protocol, TypeGuard, Union


def find_last_line(function: Union[ClassDef, FunctionDef, AsyncFunctionDef], source_lines: list[str]):
    stop = max(n.lineno for n in walk(function) if has_lineno(n))


class HasLineNo(Protocol):
    lineno: int


def has_lineno(node: AST) -> TypeGuard[HasLineNo]:
    return hasattr(node, "lineno")
