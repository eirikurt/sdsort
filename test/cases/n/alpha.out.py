class MyClass:
    def __init__(self):
        pass

    @classmethod
    def a(cls):
        pass

    def b(self):
        self.a()

    def c(self):
        self.b()
