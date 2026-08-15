from __future__ import annotations


def pluralize(count: int, word: str):
    if count != 1:
        word += "s"
    return f"{count} {word}"
