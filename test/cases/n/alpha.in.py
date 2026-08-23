class MyClass:
    def __init__(self):
        pass

    def c(self):
        self.b()

    def b(self):
        self.a()

    @classmethod
    def a(cls):
        pass
