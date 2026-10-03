class Foo:
    def helper(self):
        pass

    def closure_helper(self):
        pass

    def shadowing(self):
        def inner(self):
            self.helper()

        handler = lambda self: self.helper()
        return inner(object()), handler(object())

    def closure(self):
        def inner():
            self.closure_helper()

        return inner()
