from ast import AsyncFunctionDef, ClassDef, FunctionDef, parse

from .utils.ast import find_first_line, is_blank


def normalize_blank_lines(lines: list[str]) -> str:
    """Normalize blank lines per PEP 8:
    - 2 blank lines before top-level function/class definitions
    - 1 blank line between methods in a class (0 before the first)
    """
    # Collect 0-based line indices where PEP 8 spacing rules apply
    # Maps line_index -> required number of preceding blank lines
    required_blanks: dict[int, int] = {}
    tree = parse("\n".join(lines) + "\n")

    for node in tree.body:
        if isinstance(node, (FunctionDef, AsyncFunctionDef, ClassDef)):
            marker = find_first_line(node, lines)
            required_blanks[marker] = 2

    classNodes = [node for node in tree.body if isinstance(node, ClassDef)]
    for node in classNodes:
        methods = [n for n in node.body if isinstance(n, (FunctionDef, AsyncFunctionDef))]
        for i, method in enumerate(methods):
            marker = find_first_line(method, lines)
            has_preceding_blank = is_blank(lines[marker - 1])
            is_first_method = i == 0
            required_blanks[marker] = 1 if has_preceding_blank or not is_first_method else 0

    # Walk lines, stripping existing blank lines before def sites
    # and injecting the required number
    result: list[str] = []
    i = 0
    while i < len(lines):
        if i in required_blanks:
            # Strip any blank lines already accumulated at the end of result
            while result and is_blank(result[-1]):
                result.pop()
            # Inject the required blank lines
            result.extend([""] * required_blanks[i])
        line = lines[i]
        i += 1

        # Cap consecutive blank lines at 2 (PEP 8)
        if not is_blank(line) or len(result) < 2 or any(not is_blank(line) for line in result[-2:]):
            result.append(line)

    return "\n".join(result).strip() + "\n"
