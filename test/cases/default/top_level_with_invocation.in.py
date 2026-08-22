def setup():
    print("setup")


# This top-level call pins setup() above this line
config = setup()


def helper():
    print("helper")


def process():
    helper()
    print("process")


def main():
    process()
    print("main")
