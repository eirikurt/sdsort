from ast import AST, AsyncFunctionDef, FunctionDef, walk
from typing import Protocol, TypeGuard, Union

FunDef = Union[FunctionDef, AsyncFunctionDef]


def read_file(file_path: str) -> str:
    with open(file_path) as f:
        source = f.read()
    return _normalize_line_endings(source)


def _normalize_line_endings(input: str):
    result = input.replace("\r\n", "\n").replace("\r", "\n")
    if not result.endswith("\n"):
        result += "\n"
    return result


def determine_line_range(method: FunDef, source_lines: list[str]) -> tuple[int, int]:
    start = method.lineno
    if len(method.decorator_list) > 0:
        start = min(d.lineno for d in method.decorator_list)

    # AST line numbers are 1-based. Subtract one from the start position to make it 0-based
    start -= 1

    # Check if there are any leading comments. If so, include them as well
    peek = source_lines[start - 1] if start > 0 else ""
    while peek.strip().startswith("#"):
        start -= 1
        peek = source_lines[start - 1] if start > 0 else ""

    stop = max(n.lineno for n in walk(method) if has_lineno(n))

    # Probe a bit further until we find an empty line or one with less indentation than the method body
    peek = source_lines[stop] if stop < len(source_lines) else ""
    while peek.strip() != "" and (
        peek.startswith(" " * (method.col_offset + 1)) or peek.startswith("\t" * (method.col_offset + 1))
    ):
        stop += 1
        peek = source_lines[stop] if stop < len(source_lines) else ""

    return start, stop


class HasLineNo(Protocol):
    lineno: int


def has_lineno(node: AST) -> TypeGuard[HasLineNo]:
    return hasattr(node, "lineno")
