class Foo:
    def helper(self):
        pass

    def closure_helper(self):
        pass

    def default_helper(self):
        return 1

    def shadowing(self):
        def inner(self):
            self.helper()

        handler = lambda self: self.helper()
        return inner(object()), handler(object())

    def closure(self):
        def inner():
            self.closure_helper()

        return inner()

    def shadowing_with_default(self):
        def inner(self, value=self.default_helper()):
            return value

        return inner
