def a():
    print("a")

if True:
    x = a()


def b():
    c()


def c():
    d()


def d():
    print("d")


for _ in range(2):
    y = b()
