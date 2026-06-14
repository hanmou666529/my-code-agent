"""Tests for Semantic Cache — hash cache + BM25 fuzzy match."""

from __future__ import annotations

import json
import time
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from my_code_agent.semantic_cache import (
    BM25Index,
    CacheEntry,
    SemanticCache,
    _tokenize,
)


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------

class TestTokenize:
    def test_basic_tokenization(self):
        tokens = _tokenize("Hello world this is a test")
        assert "hello" in tokens
        assert "world" in tokens
        assert "test" in tokens
        # Stopwords should be filtered
        assert "is" not in tokens
        assert "a" not in tokens

    def test_punctuation_stripped(self):
        tokens = _tokenize("Hello, world! Test@123")
        assert "hello" in tokens
        assert "world" in tokens
        assert "test" in tokens  # @ replaced by space

    def test_short_tokens_filtered(self):
        tokens = _tokenize("a I the best")
        assert "a" not in tokens
        assert "i" not in tokens
        assert "the" not in tokens
        assert "best" in tokens


# ---------------------------------------------------------------------------
# BM25Index
# ---------------------------------------------------------------------------

class TestBM25Index:
    def test_add_and_score(self, tmp_path: Path):
        idx = BM25Index(tmp_path / "idx.json")
        idx.load()
        idx.add_document("doc1", "Python is great for coding")
        idx.add_document("doc2", "JavaScript is great for web")
        idx.save()

        results = idx.score("Python coding", top_k=2)
        assert len(results) >= 1
        assert results[0][0] == "doc1"  # Python + coding match doc1

    def test_remove_document(self, tmp_path: Path):
        idx = BM25Index(tmp_path / "idx2.json")
        idx.load()
        idx.add_document("doc1", "Python is great")
        idx.add_document("doc2", "Java is great")
        idx.remove_document("doc1")

        results = idx.score("Python")
        assert all(did != "doc1" for did, _ in results)

    def test_empty_score(self, tmp_path: Path):
        idx = BM25Index(tmp_path / "idx3.json")
        idx.load()
        results = idx.score("anything")
        assert results == []

    def test_persistence(self, tmp_path: Path):
        idx = BM25Index(tmp_path / "idx4.json")
        idx.load()
        idx.add_document("a", "hello world")
        idx.save()

        # Reload
        idx2 = BM25Index(tmp_path / "idx4.json")
        idx2.load()
        assert idx2.doc_count == 1
        results = idx2.score("hello")
        assert len(results) >= 1


# ---------------------------------------------------------------------------
# CacheEntry
# ---------------------------------------------------------------------------

class TestCacheEntry:
    def test_serialization(self):
        entry = CacheEntry(
            request_hash="abc123",
            system_prompt_hash="sys456",
            response="Hello world",
            model="test-model",
            cached_at=1000.0,
            hit_count=5,
        )
        d = entry.to_dict()
        restored = CacheEntry.from_dict(d)
        assert restored.request_hash == "abc123"
        assert restored.hit_count == 5

    def test_is_fresh(self, tmp_path: Path):
        cache = SemanticCache(tmp_path / "fresh_test")
        assert cache._is_fresh(time.time() - 60) is True
        assert cache._is_fresh(time.time() - 7200) is False  # 2 hours old


# ---------------------------------------------------------------------------
# SemanticCache
# ---------------------------------------------------------------------------

class TestSemanticCache:
    def test_exact_hit(self, tmp_path: Path):
        cache = SemanticCache(tmp_path / "cache", ttl_seconds=3600)
        cache.load()
        cache.put("What is Python?", "You are a tutor.", "tutor-model", "Python is a programming language.")
        result = cache.get("What is Python?", "You are a tutor.", "tutor-model")
        assert result is not None
        assert "Python is a programming language" in result

    def test_exact_miss(self, tmp_path: Path):
        cache = SemanticCache(tmp_path / "cache2", ttl_seconds=3600)
        cache.load()
        result = cache.get("What is Rust?", "You are a tutor.", "tutor-model")
        assert result is None

    def test_fuzzy_hit(self, tmp_path: Path):
        cache = SemanticCache(tmp_path / "cache3", ttl_seconds=3600, bm25_min_score=0.1)
        cache.load()
        cache.put("How do I sort a list in Python?", "System prompt.", "model-a",
                   "Use the sorted() function: sorted(my_list)")
        # Similar but not identical query
        result = cache.get("How to sort lists in Python?", "System prompt.", "model-a")
        assert result is not None
        assert "SEMANTIC CACHE HIT" in result

    def test_model_isolation(self, tmp_path: Path):
        cache = SemanticCache(tmp_path / "cache4")
        cache.load()
        cache.put("What is 2+2?", "Math tutor.", "math-model", "4")
        cache.put("What is 2+2?", "General bot.", "general-model", "That depends on your definition")
        # Different model should not match
        result = cache.get("What is 2+2?", "General bot.", "general-model")
        assert result is not None
        assert "definition" in result

    def test_put_eviction(self, tmp_path: Path):
        cache = SemanticCache(tmp_path / "cache5", max_entries=3)
        cache.load()
        cache.put("q1", "sp", "m", "r1")
        cache.put("q2", "sp", "m", "r2")
        cache.put("q3", "sp", "m", "r3")
        # This should evict the oldest (q1)
        cache.put("q4", "sp", "m", "r4")
        result = cache.get("q1", "sp", "m")
        assert result is None

    def test_stats(self, tmp_path: Path):
        cache = SemanticCache(tmp_path / "cache6")
        cache.load()
        cache.put("a", "s", "m", "r")
        cache.put("b", "s", "m", "r2")
        stats = cache.stats()
        assert stats["exact_entries"] == 2
        assert stats["ttl_seconds"] == 3600

    def test_clear(self, tmp_path: Path):
        cache = SemanticCache(tmp_path / "cache7")
        cache.load()
        cache.put("a", "s", "m", "r")
        cache.clear()
        assert cache.get("a", "s", "m") is None

    def test_persistence(self, tmp_path: Path):
        cache = SemanticCache(tmp_path / "cache8")
        cache.load()
        cache.put("persist-me", "sys", "m", "persisted-response")
        cache.save()

        # New cache instance loads from disk
        cache2 = SemanticCache(tmp_path / "cache8")
        cache2.load()
        result = cache2.get("persist-me", "sys", "m")
        assert result == "persisted-response"

    def test_invalid(self, tmp_path: Path):
        cache = SemanticCache(tmp_path / "cache9")
        cache.load()
        cache.put("del-me", "s", "m", "r")
        assert cache.invalidate("del-me", "s", "m") is True
        assert cache.invalidate("nonexistent", "s", "m") is False
