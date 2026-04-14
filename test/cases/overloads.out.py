from abc import ABC
from typing import overload


class MyClass(
    ABC
):
    def bar(self):
        self.foo("string")

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


def the_void():
    space(b"0")
    chamber()


@overload
def space(value: None) -> None: ...

@overload
def space(value: bytes) -> bytes: ...

def space(value):
    return value


def chamber():
    echo(b"chamber")


@overload
def echo(value: None) -> None:
    pass
@overload
def echo(value: bytes) -> bytes:
    pass
def echo(value):
    return value
