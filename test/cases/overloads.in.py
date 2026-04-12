from typing import overload


class MyClass:
    @overload
    def foo(self, something: str) -> None: ...
    @overload
    def foo(self, something: int) -> None:
        pass
    def foo(self, something: int | str) -> None:
        if isinstance(something, str):
            print("It's a string!")
        else:
            print("It's a number")

    def bar(self):
        self.foo("string")


@overload
def echo(value: None) -> None:
    pass
@overload
def echo(value: bytes) -> bytes:
    pass
def echo(value):
    return value
