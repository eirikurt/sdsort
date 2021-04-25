class CircularRef:
    def c(self):
        self.a(1000)

    def a(self, some_val: int):
        if some_val < 0:
            self.b(some_val - 1)

    def b(self, some_val: int):
        if some_val < 0:
            self.a(some_val // 2)
