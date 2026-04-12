from typing import overload


class MyClass:
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
