from ast import AsyncFunctionDef, ClassDef, FunctionDef, parse


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
            target = min((d.lineno for d in node.decorator_list), default=node.lineno)
            # Scan backwards past any leading comments so the 2 blank lines are
            # inserted before the comment block, not between the comment and the def.
            marker = target - 1  # 0-based index of the def/decorator line
            while marker > 0 and lines[marker - 1].strip().startswith("#"):
                marker -= 1
            required_blanks[marker] = 2

    for node in tree.body:
        if not isinstance(node, ClassDef):
            continue
        methods = [n for n in node.body if isinstance(n, (FunctionDef, AsyncFunctionDef))]
        for i, method in enumerate(methods):
            target = min((d.lineno for d in method.decorator_list), default=method.lineno)
            if i == 0:
                # For the first method, preserve existing blank lines (up to 1) rather
                # than forcing 0 — this allows a blank between class variables and the
                # first method when the author already wrote one.
                preceding_blanks = 0
                for line_idx in range(target - 2, -1, -1):
                    if lines[line_idx].strip() == "":
                        preceding_blanks += 1
                    else:
                        break
                required_blanks[target - 1] = min(preceding_blanks, 1)
            else:
                required_blanks[target - 1] = 1  # 0-based

    # Walk lines, stripping existing blank lines before def sites
    # and injecting the required number
    result: list[str] = []
    i = 0
    while i < len(lines):
        if i in required_blanks:
            # Strip any blank lines already accumulated at the end of result
            while result and result[-1].strip() == "":
                result.pop()
            # Inject the required blank lines
            result.extend([""] * required_blanks[i])
        line = lines[i]
        # Cap consecutive blank lines at 2 (PEP 8) for lines not controlled by required_blanks
        if (
            i not in required_blanks
            and line.strip() == ""
            and len(result) >= 2
            and result[-1].strip() == ""
            and result[-2].strip() == ""
        ):
            i += 1
            continue
        result.append(line)
        i += 1

    return "\n".join(result).strip() + "\n"
