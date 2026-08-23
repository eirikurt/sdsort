from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sdsort.config import MethodVisibility


def determine_visibility(name: str) -> MethodVisibility:
    if name.startswith("__"):
        if name.endswith("__"):
            return "dunder"
        else:
            return "private"
    elif name.startswith("_"):
        return "protected"
    else:
        return "public"
