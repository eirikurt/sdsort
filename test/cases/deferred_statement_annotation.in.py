from __future__ import annotations

from collections.abc import Callable

_STRATEGIES: dict[str, Callable[[Expr], Expr]] = {
    "double": lambda expr: expr.add(expr),
}


class Expr:
    def add(self, other: Expr) -> Expr:
        return other
