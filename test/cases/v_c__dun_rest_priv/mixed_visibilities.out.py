class Service:
    def __init__(self):
        pass

    def public_api(self):
        self._protected_leaf()

    def _protected_leaf(self):
        pass

    def public_helper(self):
        self._protected_helper()

    def _protected_helper(self):
        pass

    def __private(self):
        pass
