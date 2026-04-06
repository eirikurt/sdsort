from ast import AST, AsyncFunctionDef, FunctionDef, walk
from itertools import takewhile
from typing import Protocol, TypeGuard, Union

FunDef = Union[FunctionDef, AsyncFunctionDef]


def read_file(file_path: str) -> str:
    with open(file_path) as f:
        source = f.read()
    return normalize_line_endings(source)


def normalize_line_endings(input: str):
    result = input.replace("\r\n", "\n").replace("\r", "\n")
    if not result.endswith("\n"):
        result += "\n"
    return result


def determine_line_range(function: FunDef, source_lines: list[str]) -> tuple[int, int]:
    start = _find_start(function, source_lines)
    stop = _find_stop(function, source_lines)
    return start, stop


def _find_start(function: FunDef, source_lines: list[str]) -> int:
    start = function.lineno
    if len(function.decorator_list) > 0:
        start = min(d.lineno for d in function.decorator_list)

    # AST line numbers are 1-based. Subtract one from the start position to make it 0-based
    start -= 1

    # Check if there are any leading comments. If so, include them as well
    preceding_lines = source_lines[0:start]
    for _ in takewhile(is_comment, reversed(preceding_lines)):
        start -= 1

    return start


def _find_stop(function: FunDef, source_lines: list[str]) -> int:
    stop = max(n.lineno for n in walk(function) if has_lineno(n))

    # Probe a bit further until we find an empty line or one with less indentation than the method body
    def should_stop(line: str):
        return line.isspace() or count_leading_whitespace_chars(line) <= function.col_offset

    subsequent_lines = source_lines[stop:]
    for _ in takewhile(lambda line: not should_stop(line), subsequent_lines):
        stop += 1

    return stop


class HasLineNo(Protocol):
    lineno: int


def has_lineno(node: AST) -> TypeGuard[HasLineNo]:
    return hasattr(node, "lineno")


def is_comment(line: str):
    return line.strip().startswith("#")


def count_leading_whitespace_chars(line: str):
    count = 0
    for _ in takewhile(lambda x: x == " " or x == "\t", line):
        count += 1
    return count
