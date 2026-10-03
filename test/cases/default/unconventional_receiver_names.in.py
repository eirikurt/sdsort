class Foo:
    def helper(this):
        pass

    @classmethod
    def build(klass):
        return klass.create()

    @classmethod
    def create(klass):
        return klass()

    def run(this):
        this.helper()
