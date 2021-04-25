class FunctionNester:
    def bar(self):
        return self.nest("something")

    def nest(self, val: str):
        def inner():
            print(val)

        return inner
