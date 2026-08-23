def _generate_markdown(full_path: str, class_name: str) -> str:
    return f"""# {class_name}

::: {full_path}
"""


def main() -> None:
    result = _generate_markdown("foo.Bar", "Bar")
    print(result)
