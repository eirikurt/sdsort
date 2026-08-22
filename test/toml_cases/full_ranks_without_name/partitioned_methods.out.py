class Service:
    def __dunder_b__(self):
        pass

    def __dunder_a__(self):
        pass

    def public_b(self):
        pass

    def public_a(self):
        self.public_helper()
        self._private_helper()

    def public_helper(self):
        pass

    def _private_helper(self):
        pass
