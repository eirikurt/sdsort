class FunctionNester:
    def nest(self, val: str):
        def inner():
            print(val)

        return inner

    def bar(self):
        return self.nest("something")
