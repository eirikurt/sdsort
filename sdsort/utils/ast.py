from ast import AST, AsyncFunctionDef, ClassDef, FunctionDef, walk
from itertools import takewhile
from typing import Protocol, TypeGuard, Union

Function = Union[FunctionDef, AsyncFunctionDef]
ClassOrFunction = Union[ClassDef, Function]


def determine_line_range(class_or_function: ClassOrFunction, source_lines: list[str]) -> tuple[int, int]:
    start = find_first_line(class_or_function, source_lines)
    stop = find_last_line(class_or_function, source_lines)
    return start, stop


def find_first_line(class_or_function: ClassOrFunction, source_lines: list[str]) -> int:
    start = min((d.lineno for d in class_or_function.decorator_list), default=class_or_function.lineno)

    # AST line numbers are 1-based. Subtract one from the start position to make it 0-based
    start -= 1

    # Check if there are any leading comments. If so, include them as well
    preceding_lines = source_lines[0:start]
    for _ in takewhile(is_comment, reversed(preceding_lines)):
        start -= 1

    return start


def find_last_line(function: ClassOrFunction, source_lines: list[str]) -> int:
    stop = max(n.lineno for n in walk(function) if has_lineno(n))

    # Probe a bit further until we find a blank line or one with less indentation than the function/class body
    def should_continue(line: str):
        return is_blank(line) is False and count_leading_whitespace_chars(line) > function.col_offset

    subsequent_lines = source_lines[stop:]
    for _ in takewhile(should_continue, subsequent_lines):
        stop += 1

    return stop


class HasLineNo(Protocol):
    lineno: int


def has_lineno(node: AST) -> TypeGuard[HasLineNo]:
    return hasattr(node, "lineno")


def is_blank(line: str):
    return len(line) == 0 or line.isspace()


def is_comment(line: str):
    return line.strip().startswith("#")


def count_leading_whitespace_chars(line: str):
    count = 0
    for _ in takewhile(lambda x: x == " " or x == "\t", line):
        count += 1
    return count
