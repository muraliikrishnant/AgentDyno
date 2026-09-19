from broken import dedupe


def test_dedupe_preserves_order():
    assert dedupe([1, 2, 2, 3, 1]) == [1, 2, 3]


def test_dedupe_empty():
    assert dedupe([]) == []
