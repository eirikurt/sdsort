from pathlib import Path


def read_file(file_path: str | Path) -> str:
    with open(file_path, encoding="utf-8", newline=None) as f:
        return f.read()


def split_lines(source: str) -> list[str]:
    """Split source into lines the way Python's tokenizer does, 
    as opposed to what str.splitlines does.
    """
    if not source:
        return []
    lines = source.split("\n")
    if source.endswith("\n"):
        lines.pop()
    return lines
