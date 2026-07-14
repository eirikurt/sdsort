def invoke():
    return 1


class Runner:
    invoke = staticmethod(invoke)


def run():
    return invoke()
