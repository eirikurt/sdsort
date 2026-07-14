def helper():
    print("helper")


def process():
    helper()


def main():
    process()
    return MyClass()


class BaseClass:
    pass


class MyClass(BaseClass):
    def inner(self):
        print("inner")

    def outer(self):
        self.inner()

    def calls_top_level_function(self):
        process()
