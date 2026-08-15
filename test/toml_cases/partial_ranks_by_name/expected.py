class Service:
    def __init__(self):
        pass

    def __private(self):
        pass

    def _protected_helper(self):
        pass

    def _protected_leaf(self):
        pass

    def public_api(self):
        self._protected_leaf()

    def public_helper(self):
        self._protected_helper()
