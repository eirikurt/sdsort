class Foo:
    @classmethod
    def b(cls):
        pass

    @classmethod
    def a(cls):
        cls.b()
    