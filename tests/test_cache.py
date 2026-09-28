"""Tests for the generation cache."""

import pytest

from src.cache.store import GenerationCache


@pytest.fixture
def cache(tmp_path):
    c = GenerationCache(db_path=tmp_path / "test_cache.db")
    yield c
    c.close()


def test_put_and_get(cache):
    cache.put("model1", "prompt1", {"temperature": 0.0}, "Hello world")
    result = cache.get("model1", "prompt1", {"temperature": 0.0})
    assert result == "Hello world"


def test_miss_returns_none(cache):
    result = cache.get("model1", "prompt1", {"temperature": 0.0})
    assert result is None


def test_different_params_different_entries(cache):
    cache.put("m1", "p1", {"temperature": 0.0}, "deterministic")
    cache.put("m1", "p1", {"temperature": 0.7}, "sampled")
    assert cache.get("m1", "p1", {"temperature": 0.0}) == "deterministic"
    assert cache.get("m1", "p1", {"temperature": 0.7}) == "sampled"


def test_overwrite(cache):
    cache.put("m1", "p1", {"temperature": 0.0}, "first")
    cache.put("m1", "p1", {"temperature": 0.0}, "second")
    assert cache.get("m1", "p1", {"temperature": 0.0}) == "second"
