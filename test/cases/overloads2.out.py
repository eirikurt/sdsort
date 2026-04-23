from typing import Self, overload, override

type IntoExpr = int | str | Expr


class Expr:
    def __and__(self, other: IntoExpr) -> Self:  # noqa: D105
        return self

    def __or__(self, other: IntoExpr) -> Self:  # noqa: D105
        return self


class Selector(Expr):
    @overload
    def union(self, other: Self) -> Self: ...
    @overload
    def union(self, other: IntoExpr) -> Expr: ...
    def union(self, other: IntoExpr) -> Self | Expr:  # noqa: D102
        match other:
            case Selector():
                return self.into_selector()
            case _:
                return super().__or__(other)

    @overload
    def __or__(self, other: Self) -> Self: ...
    @overload
    def __or__(self, other: IntoExpr) -> Expr: ...
    @override
    def __or__(self, other: IntoExpr) -> Self | Expr:
        return self.union(other)

    def into_selector(self) -> Self:  # noqa: D102
        return self

    @overload
    def intersection(self, other: Self) -> Self: ...
    @overload
    def intersection(self, other: IntoExpr) -> Expr: ...
    def intersection(self, other: IntoExpr) -> Self | Expr:  # noqa: D102
        match other:
            case Selector():
                return self
            case _:
                return super().__and__(other)

    @overload
    def __and__(self, other: Self) -> Self: ...
    @overload
    def __and__(self, other: IntoExpr) -> Expr: ...
    @override
    def __and__(self, other: IntoExpr) -> Self | Expr:
        return self.intersection(other)
