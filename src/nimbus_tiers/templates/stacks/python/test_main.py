from main import greet


def test_greet() -> None:
    assert greet() == "Hello, World!"
