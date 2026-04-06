def read_file(file_path: str) -> str:
    with open(file_path) as f:
        source = f.read()
    return normalize_line_endings(source)


def normalize_line_endings(input: str):
    result = input.replace("\r\n", "\n").replace("\r", "\n")
    if not result.endswith("\n"):
        result += "\n"
    return result
