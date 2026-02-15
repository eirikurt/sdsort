def a():
    print("a")

if True:
    x = a()


def d():
    print("d")


def c():
    d()


def b():
    c()


for _ in range(2):
    y = b()
