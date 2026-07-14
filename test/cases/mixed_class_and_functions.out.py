def main():
    process()
    return MyClass()


class BaseClass:
    pass


class MyClass(BaseClass):
    def outer(self):
        self.inner()

    def inner(self):
        print("inner")

    def calls_top_level_function(self):
        process()


def process():
    helper()


def helper():
    print("helper")
