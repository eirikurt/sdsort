from typing import overload


class Service:
    def public_z(self):
        self.public_a()
        self._protected_entry()
        self.__validate()
        self.__validate__()

    def public_a(self):
        self.public_helper()
        self._protected_dispatch(1)
        self.__validate()

    def public_helper(self):
        self.__validate__()

    def _protected_entry(self):
        self._protected_leaf()
        self._protected_dispatch(1)

    @overload
    def _protected_dispatch(self, value: int) -> int: ...

    @overload
    def _protected_dispatch(self, value: str) -> str: ...

    def _protected_dispatch(self, value: int | str) -> int | str:
        return self._protected_leaf()

    def _protected_leaf(self) -> int | str:
        return 0

    def __validate(self):
        self.__validate__()

    def __validate__(self):
        pass
