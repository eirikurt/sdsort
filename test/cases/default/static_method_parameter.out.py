class Foo:
    def helper(self):
        pass

    @staticmethod
    def compare(left, right):
        return left.helper() == right.helper()
