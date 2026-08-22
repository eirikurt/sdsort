class Service:
    def __init__(self):
        pass

    def _protected(self):
        pass

    def public_b(self):
        pass

    def public_z(self):
        self.public_a()

    def public_a(self):
        pass
