import logging
from datetime import date
from functools import partial


def power(base, exponent):
    return base ** exponent


logger = logging.getLogger(__name__)
square = partial(power, exponent=2)


def greet(person: str, extra: str):
    logger.info("Greet was called")
    print(f"Greetings {person}. {extra}")


if date.today().isoweekday == 5:
    say_hi = partial(greet, extra="It's Friday!")
else:
    say_hi = partial(greet, extra="Meh.")


def main():
    say_hi(f"John {square(4)}")
