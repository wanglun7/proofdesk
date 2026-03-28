import pytest
from services.retrieval import cosine_top_k_mock


def test_cosine_top_k_mock_returns_sorted():
    items = [("a", 0.5), ("b", 0.9), ("c", 0.3)]
    result = cosine_top_k_mock(items, top_k=2)
    assert result[0][1] >= result[1][1]
    assert len(result) == 2


def test_cosine_top_k_mock_returns_all_if_fewer():
    items = [("a", 0.5)]
    result = cosine_top_k_mock(items, top_k=10)
    assert len(result) == 1


def test_cosine_top_k_mock_empty():
    result = cosine_top_k_mock([], top_k=5)
    assert result == []
