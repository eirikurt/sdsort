def run():
    return invoke()


def invoke():
    return 1


class Runner:
    invoke = staticmethod(invoke)
