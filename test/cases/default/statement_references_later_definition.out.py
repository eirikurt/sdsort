from functools import partial


def compute():
    return power(2, 3)


def power(base, exponent):
    return base ** exponent


square = partial(power, exponent=2)
