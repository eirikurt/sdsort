from pathlib import Path


def read_file(file_path: str | Path) -> str:
    with open(file_path, encoding="utf-8", newline=None) as f:
        return f.read()


def split_lines(source: str) -> list[str]:
    """Split source into lines the way Python's tokenizer does.

    Unlike ``str.splitlines()``, this only breaks on newlines (``\\n``) and not on
    other characters such as form feeds (``\\f``) or vertical tabs, which the AST
    treats as in-line whitespace. ``read_file`` reads in universal-newline mode, so
    ``\\r\\n``/``\\r`` are already normalised to ``\\n`` by the time we get here.
    Keeping the split consistent with the AST's line numbering is essential: the
    block line ranges are derived from AST ``lineno``/``end_lineno``.
    """
    if not source:
        return []
    lines = source.split("\n")
    if source.endswith("\n"):
        lines.pop()
    return lines
