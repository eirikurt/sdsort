def helper():
    print("helper")


def process():
    helper()


def main():
    process()


class MyClass:
    def inner(self):
        print("inner")

    def outer(self):
        self.inner()
