class Foo:
    @classmethod
    def a(cls):
        cls.b()

    @classmethod
    def b(cls):
        pass
