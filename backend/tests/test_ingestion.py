import pytest
from services.ingestion import chunk_text


def test_chunk_text_splits_long_text():
    text = "word " * 600  # ~3000 words
    chunks = chunk_text(text, chunk_size=500, overlap=50)
    assert len(chunks) > 1
    # each chunk has at most 500 words — join back and count
    for c in chunks:
        assert len(c.split()) <= 500


def test_chunk_text_short_text():
    text = "short text"
    chunks = chunk_text(text, chunk_size=500, overlap=50)
    assert chunks == ["short text"]


def test_chunk_text_empty():
    chunks = chunk_text("", chunk_size=500, overlap=50)
    assert chunks == []
