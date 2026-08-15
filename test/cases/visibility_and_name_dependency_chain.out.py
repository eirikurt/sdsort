class Service:
    def __private_a(self):
        pass

    def __private_z(self):
        pass

    def public_a(self):
        self.public_z()

    def public_z(self):
        self.public_helper()

    def public_helper(self):
        pass

    def public_b(self):
        pass

    def _protected_a(self):
        pass

    def _protected_z(self):
        pass

    def __dunder_a__(self):
        pass

    def __dunder_z__(self):
        pass
