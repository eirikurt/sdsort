class CircularRef:
    def c(self):
        self.a(1000)

    def a(self, some_val: int):
        if some_val < 0:
            self.b(some_val - 1)

    def b(self, some_val: int):
        if some_val < 0:
            self.a(some_val // 2)


class Selector():
    def __or__(self, other):
        return self.union(other)

    def union(self, other):  # noqa: D102
        match other:
            case Selector():
                return 1
            case _:
                return super().__or__(other)
