import pytest

@pytest.fixture
def prepare_stuff():
    def _inner():
        return 2
    
    return _inner


def test_something(prepare_stuff):
    x = prepare_stuff()
    do_stuff()
    assert x > 0


def do_stuff():
    print("doing")
