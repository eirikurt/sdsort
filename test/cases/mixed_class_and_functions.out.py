def main():
    process()


def process():
    helper()


def helper():
    print("helper")


class MyClass:
    def outer(self):
        self.inner()

    def inner(self):
        print("inner")
