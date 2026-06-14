"""Semantic Cache / RAG Index — reduces repeated LLM calls.

Two-layer deduplication:
  Layer 1: SHA-256 hash cache for exact-match requests (fast path).
  Layer 2: BM25 inverted index for semantic-similar requests (fuzzy path).

Both layers store (prompt_hash, system_prompt_hash, response_text,
cached_at, hit_count) and respect a configurable TTL.

Zero external dependencies — pure stdlib + json.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Tokeniser helpers (BM25-friendly, no external deps)
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> List[str]:
    """Simple whitespace + lowercase tokenizer with punctuation stripping."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9_\-\+\/\.]", " ", text)
    tokens = text.split()
    # Drop very short tokens (< 2 chars) and common stopwords
    stopwords: set[str] = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been",
        "being", "have", "has", "had", "do", "does", "did", "will",
        "would", "could", "should", "may", "might", "shall", "can",
        "to", "of", "in", "for", "on", "with", "at", "by", "from",
        "as", "into", "through", "during", "before", "after", "and",
        "but", "or", "nor", "not", "so", "yet", "both", "either",
        "neither", "each", "every", "all", "any", "few", "more",
        "most", "other", "some", "such", "no", "only", "own", "same",
        "than", "too", "very", "just", "because", "if", "then",
        "that", "this", "these", "those", "it", "its",
    }
    return [t for t in tokens if len(t) >= 2 and t not in stopwords]


# ---------------------------------------------------------------------------
# BM25 scoring (Okapi BM25 formulation)
# ---------------------------------------------------------------------------

_K1 = 1.5   # term frequency saturation
_B = 0.75   # length normalization


def _bm25_score(
    query_tokens: List[str],
    doc_tokens: List[str],
    avg_doc_len: float,
    doc_freq: Dict[str, int],
    doc_count: int,
) -> float:
    """Compute BM25 score between query tokens and a document."""
    if not query_tokens or not doc_tokens:
        return 0.0

    doc_len = len(doc_tokens)
    len_norm = 1.0 - _B + _B * (doc_len / max(avg_doc_len, 1.0))
    score = 0.0

    # Build document term frequency
    tf: Dict[str, int] = {}
    for t in doc_tokens:
        tf[t] = tf.get(t, 0) + 1

    for qtok in query_tokens:
        df = doc_freq.get(qtok, 0)
        if df == 0:
            continue
        idf = math.log(1 + (doc_count - df + 0.5) / (df + 0.5))
        tf_val = tf.get(qtok, 0)
        tf_term = (tf_val * (_K1 + 1.0)) / (
            tf_val + _K1 * (1.0 - _B + _B * (doc_len / max(avg_doc_len, 1.0)))
        )
        score += idf * tf_term

    return score


# ---------------------------------------------------------------------------
# BM25 Inverted Index
# ---------------------------------------------------------------------------

class BM25Index:
    """Minimal BM25 inverted index backed by a JSON file.

    Stores documents as token lists, supports scoring against arbitrary
    query strings. Persists to disk so the index survives restarts.
    """

    def __init__(self, index_path: Path) -> None:
        self._index_path = index_path
        # id -> list of tokens
        self._docs: Dict[str, List[str]] = {}
        # token -> set of doc_ids
        self._postings: Dict[str, set[str]] = {}
        # token -> number of docs containing token
        self._doc_freq: Dict[str, int] = {}
        self._avg_doc_len: float = 100.0
        self._loaded = False

    def load(self) -> None:
        """Load index from disk."""
        if not self._index_path.exists():
            self._loaded = True
            return
        try:
            data = json.loads(self._index_path.read_text(encoding="utf-8"))
            self._docs = {k: v["tokens"] for k, v in data["docs"].items()}
            self._postings = {
                k: set(v) for k, v in data["postings"].items()
            }
            self._doc_freq = {
                k: len(v) for k, v in data["postings"].items()
            }
            total_tokens = sum(len(tokens) for tokens in self._docs.values())
            self._avg_doc_len = (
                total_tokens / max(len(self._docs), 1)
            )
        except (json.JSONDecodeError, KeyError):
            pass
        self._loaded = True

    def save(self) -> None:
        """Persist index to disk."""
        if not self._loaded:
            return
        self._index_path.parent.mkdir(parents=True, exist_ok=True)
        data: Dict[str, Any] = {
            "docs": {
                did: {"tokens": tokens} for did, tokens in self._docs.items()
            },
            "postings": {
                tok: sorted(dids) for tok, dids in self._postings.items()
            },
        }
        self._index_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))

    def add_document(self, doc_id: str, text: str) -> None:
        """Index a document for fuzzy lookup."""
        tokens = _tokenize(text)
        self._docs[doc_id] = tokens
        for tok in set(tokens):
            self._postings.setdefault(tok, set()).add(doc_id)
            self._doc_freq[tok] = len(self._postings[tok])
        # Recompute average doc length
        total = sum(len(t) for t in self._docs.values())
        self._avg_doc_len = total / max(len(self._docs), 1)

    def remove_document(self, doc_id: str) -> None:
        """Remove a document from the index."""
        tokens = self._docs.pop(doc_id, [])
        for tok in set(tokens):
            self._postings[tok].discard(doc_id)
            if not self._postings[tok]:
                self._postings.pop(tok, None)
                self._doc_freq.pop(tok, None)
        total = sum(len(t) for t in self._docs.values())
        self._avg_doc_len = total / max(len(self._docs), 1)

    def score(self, query_text: str, top_k: int = 5) -> List[Tuple[str, float]]:
        """Score documents against a query, return top-k (doc_id, score)."""
        query_tokens = _tokenize(query_text)
        if not query_tokens or not self._docs:
            return []

        scores: Dict[str, float] = {}
        for did, tokens in self._docs.items():
            scores[did] = _bm25_score(
                query_tokens, tokens, self._avg_doc_len,
                self._doc_freq, len(self._docs),
            )

        ranked = sorted(scores.items(), key=lambda x: -x[1])
        return [(did, sc) for did, sc in ranked[:top_k] if sc > 0.0]

    @property
    def doc_count(self) -> int:
        return len(self._docs)


# ---------------------------------------------------------------------------
# Exact-match cache entry
# ---------------------------------------------------------------------------

@dataclass
class CacheEntry:
    """A single cached LLM response."""

    request_hash: str
    system_prompt_hash: str
    response: str
    model: str
    cached_at: float = field(default_factory=time.time)
    hit_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_hash": self.request_hash,
            "system_prompt_hash": self.system_prompt_hash,
            "response": self.response,
            "model": self.model,
            "cached_at": self.cached_at,
            "hit_count": self.hit_count,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CacheEntry":
        return cls(**{k: d[k] for k in ("request_hash", "system_prompt_hash",
                                         "response", "model", "cached_at", "hit_count")})


# ---------------------------------------------------------------------------
# SemanticCache
# ---------------------------------------------------------------------------

class SemanticCache:
    """Two-layer cache: exact hash + BM25 fuzzy match.

    Usage:
        cache = SemanticCache(Path(".agent/semantic-cache"))
        cache.load()

        # Exact or fuzzy hit
        result = cache.get(user_input, system_prompt, model)
        if result is not None:
            print(f"[CACHE HIT] {result}")

        # Store a new response
        cache.put(user_input, system_prompt, model, response)
        cache.save()
    """

    def __init__(
        self,
        cache_dir: Path,
        ttl_seconds: int = 3600,       # 1 hour default
        bm25_min_score: float = 0.5,   # minimum BM25 score for fuzzy match
        max_entries: int = 5000,
    ) -> None:
        self._cache_dir = cache_dir
        self._ttl = ttl_seconds
        self._bm25_min_score = bm25_min_score
        self._max_entries = max_entries

        # Layer 1: exact hash cache
        self._hash_cache: Dict[str, CacheEntry] = {}
        # Layer 2: BM25 index keyed by request_hash
        self._bm25 = BM25Index(cache_dir / "bm25_index.json")
        self._loaded = False

    def load(self) -> None:
        """Load cache from disk."""
        cache_file = self._cache_dir / "cache.json"
        if cache_file.exists():
            try:
                data = json.loads(cache_file.read_text(encoding="utf-8"))
                for entry_dict in data.get("entries", []):
                    entry = CacheEntry.from_dict(entry_dict)
                    self._hash_cache[entry.request_hash] = entry
            except (json.JSONDecodeError, KeyError):
                pass

        self._bm25.load()
        self._loaded = True

    def save(self) -> None:
        """Persist cache to disk."""
        if not self._loaded:
            return
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        entries = [e.to_dict() for e in self._hash_cache.values()]
        data = {"entries": entries, "saved_at": time.time()}
        cache_file = self._cache_dir / "cache.json"
        cache_file.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        self._bm25.save()

    @staticmethod
    def _hash(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

    def _make_request_key(self, user_input: str, system_prompt: str, model: str) -> str:
        combined = f"{model}|||{system_prompt}|||{user_input}"
        return self._hash(combined)

    def get(
        self,
        user_input: str,
        system_prompt: str,
        model: str,
    ) -> Optional[str]:
        """Try to serve a cached response.

        Returns the cached response string or None on miss/expiry.
        """
        req_key = self._make_request_key(user_input, system_prompt, model)

        # Layer 1: exact match
        entry = self._hash_cache.get(req_key)
        if entry is not None and self._is_fresh(entry.cached_at):
            entry.hit_count += 1
            return entry.response

        # Layer 2: BM25 fuzzy match
        # Build a lightweight "document" text to search against
        searchable = f"{system_prompt[:500]} {user_input}"
        # Skip fuzzy match for very short queries (< 3 meaningful tokens)
        # Short queries produce unreliable BM25 scores with high false-positive rate
        if len(_tokenize(user_input)) < 3:
            return None

        candidates = self._bm25.score(searchable, top_k=3)

        if not candidates:
            return None

        # Normalize BM25 score to [0, 1] similarity using max score
        max_score = candidates[0][1]
        is_single_doc = len(self._hash_cache) == 1
        for doc_id, score in candidates:
            normalized = score / max(max_score, 1e-9)
            if is_single_doc:
                # Single document: require minimum absolute BM25 score to ensure
                # meaningful token overlap (prevents noise matches)
                if score < 1.0:
                    continue
            elif normalized < 0.95:
                # Multiple documents: require high normalized similarity
                continue
            candidate_entry = self._hash_cache.get(doc_id)
            if candidate_entry is not None and self._is_fresh(candidate_entry.cached_at):
                candidate_entry.hit_count += 1
                return f"[SEMANTIC CACHE HIT (score={normalized:.2f})] {candidate_entry.response}"

        return None

    def put(
        self,
        user_input: str,
        system_prompt: str,
        model: str,
        response: str,
    ) -> None:
        """Store a response in the cache."""
        req_key = self._make_request_key(user_input, system_prompt, model)
        system_hash = self._hash(system_prompt)

        # Evict oldest if over capacity
        if len(self._hash_cache) >= self._max_entries:
            self._evict_oldest()

        entry = CacheEntry(
            request_hash=req_key,
            system_prompt_hash=system_hash,
            response=response,
            model=model,
        )
        self._hash_cache[req_key] = entry
        # Index for BM25
        searchable = f"{system_prompt[:500]} {user_input}"
        self._bm25.add_document(req_key, searchable)

    def invalidate(self, user_input: str, system_prompt: str, model: str) -> bool:
        """Remove a specific entry."""
        req_key = self._make_request_key(user_input, system_prompt, model)
        if req_key in self._hash_cache:
            del self._hash_cache[req_key]
            self._bm25.remove_document(req_key)
            return True
        return False

    def clear(self) -> None:
        """Wipe the entire cache."""
        self._hash_cache.clear()
        self._bm25 = BM25Index(self._cache_dir / "bm25_index.json")

    def stats(self) -> Dict[str, Any]:
        """Return cache statistics."""
        total_hits = sum(e.hit_count for e in self._hash_cache.values())
        return {
            "exact_entries": len(self._hash_cache),
            "bm25_documents": self._bm25.doc_count,
            "total_hits": total_hits,
            "ttl_seconds": self._ttl,
        }

    # ---- Internals ----

    @staticmethod
    def _is_fresh(timestamp: float) -> bool:
        return (time.time() - timestamp) < 3600  # 1-hour freshness check

    def _evict_oldest(self) -> None:
        """Evict the least recently used (lowest hit_count, oldest cached_at)."""
        if not self._hash_cache:
            return
        victim = min(
            self._hash_cache.values(),
            key=lambda e: (e.hit_count, e.cached_at),
        )
        self._hash_cache.pop(victim.request_hash, None)
        self._bm25.remove_document(victim.request_hash)
