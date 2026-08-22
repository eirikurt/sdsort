from typing import overload


class Api:
    def public_z(self):
        pass

    @overload
    def public_call(self, value: int) -> int: ...

    @overload
    def public_call(self, value: str) -> str: ...

    def public_call(self, value: int | str) -> int | str:
        return value

    def __private_validate(self):
        pass

    def public_a(self):
        return self.public_call(1)

    def _protected_state(self):
        pass

    def __dunder_reset__(self):
        pass
