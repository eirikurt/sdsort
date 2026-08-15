class Handler:
    def public_a(self):
        self._protected_helper()
        self.__private_helper()
        self.__dunder_helper__()

    def public_b(self):
        pass

    def public_c(self):
        pass

    def _protected_helper(self):
        pass

    def __private_helper(self):
        pass

    def __dunder_helper__(self):
        pass
