def read_file(file_path: str) -> str:
    with open(file_path, encoding="utf-8", newline=None) as f:
        return f.read()
