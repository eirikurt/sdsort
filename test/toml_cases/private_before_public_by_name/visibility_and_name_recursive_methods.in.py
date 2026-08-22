class RecursiveService:
    def public_z(self):
        pass

    def _protected_state(self):
        pass

    def __private_reset(self):
        pass

    def public_beta(self):
        self.public_alpha()

    def __dunder_b__(self):
        pass

    def public_alpha(self):
        self.public_beta()

    def _protected_start(self):
        pass

    def __dunder_a__(self):
        pass
