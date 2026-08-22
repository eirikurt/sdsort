def setup():
    print("setup")


# This top-level call pins setup() above this line
config = setup()


def main():
    process()
    print("main")


def process():
    helper()
    print("process")


def helper():
    print("helper")
