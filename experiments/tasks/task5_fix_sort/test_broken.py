from broken import bubble_sort


def test_sort_ascending():
    assert bubble_sort([3, 1, 2]) == [1, 2, 3]


def test_sort_already_sorted():
    assert bubble_sort([1, 2, 3]) == [1, 2, 3]
