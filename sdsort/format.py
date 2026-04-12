from ast import AsyncFunctionDef, FunctionDef, Module, parse

from .utils.ast import find_first_line, get_class_nodes, get_function_and_class_nodes, get_method_nodes, is_blank


def normalize_blank_lines(lines: list[str]) -> str:
    """Normalize blank lines per PEP 8:
    - 2 blank lines before top-level function/class definitions
    - 1 blank line between methods in a class (0 before the first)
    - Then there are a few exceptions, like allowing 0 lines between overload defs
    """
    tree = parse("\n".join(lines) + "\n")
    required_blanks = _find_where_blanks_should_be(tree, lines)
    reformatted_lines = _adjust_blank_lines(lines, required_blanks)
    return "\n".join(reformatted_lines).strip() + "\n"


def _find_where_blanks_should_be(ast: Module, lines: list[str]):
    """Collect 0-based line indices where PEP 8 spacing rules apply.
    Maps line_index -> required number of preceding blank lines.
    """
    required_top_level_blanks = _find_required_top_level_blanks(ast, lines)
    required_class_method_blanks = _find_required_class_method_blanks(ast, lines)
    return required_top_level_blanks | required_class_method_blanks


def _find_required_top_level_blanks(ast: Module, lines: list[str]):
    required_blanks: dict[int, int] = {}
    seen_functions = set[str]()
    for node in get_function_and_class_nodes(ast):
        if isinstance(node, (FunctionDef, AsyncFunctionDef)):
            if node.name in seen_functions:
                continue
            seen_functions.add(node.name)
        line_index = find_first_line(node, lines)
        required_blanks[line_index] = 2
    return required_blanks


def _find_required_class_method_blanks(ast, lines):
    required_blanks: dict[int, int] = {}
    for class_node in get_class_nodes(ast):
        seen_methods = set[str]()
        for i, method in enumerate(get_method_nodes(class_node)):
            if method.name in seen_methods:
                continue
            seen_methods.add(method.name)
            line_index = find_first_line(method, lines)
            has_preceding_blank = is_blank(lines[line_index - 1])
            is_first_method = i == 0
            required_blanks[line_index] = 1 if has_preceding_blank or not is_first_method else 0
    return required_blanks


def _adjust_blank_lines(lines: list[str], required_blanks: dict[int, int]):
    result: list[str] = []
    for i, line in enumerate(lines):
        if i in required_blanks:
            # Strip any blank lines already accumulated at the end of result
            while result and is_blank(result[-1]):
                result.pop()

            # Inject the required blank lines
            result.extend([""] * required_blanks[i])

        # Append current line, as long as that doesn't result in 3 blank lines in succession
        if not is_blank(line) or len(result) < 2 or any(not is_blank(line) for line in result[-2:]):
            result.append(line)

    return result
