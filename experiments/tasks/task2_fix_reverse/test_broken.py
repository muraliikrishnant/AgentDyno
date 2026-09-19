from broken import reverse_string


def test_reverse_basic():
    assert reverse_string("abc") == "cba"


def test_reverse_empty():
    assert reverse_string("") == ""
