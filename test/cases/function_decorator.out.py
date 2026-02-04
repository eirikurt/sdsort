def my_decorator(func):
    def wrapper(*args, **kwargs):
        print("before")
        result = func(*args, **kwargs)
        print("after")
        return result
    return wrapper


@my_decorator
def main():
    helper()


def helper():
    print("helper")
