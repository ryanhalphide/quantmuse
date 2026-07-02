"""
Embedding Manager
Turns text into vector embeddings for use with VectorStore.

Backends (selected at construction, or auto-detected):
  - "sentence_transformers": local HuggingFace sentence-transformers model
  - "openai":               OpenAI embeddings API (needs an API key)
  - "hash":                 dependency-free deterministic hashing embedding,
                            useful offline and in tests

VectorStore.add_document / search_similar expect pre-computed embeddings, so
this class is the natural front-end: generate an embedding here, then hand it
to the store.
"""

import hashlib
import logging
from typing import Dict, List, Optional

import numpy as np

# Optional backends — detected at import, mirroring the project convention.
try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False

try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


class EmbeddingManager:
    """Generate and cache text embeddings for the vector store."""

    # Sensible default models per backend.
    DEFAULT_MODELS = {
        "sentence_transformers": "all-MiniLM-L6-v2",
        "openai": "text-embedding-3-small",
        "hash": "hash-256",
    }
    # Output dimension for the dependency-free hash backend.
    HASH_DIM = 256

    def __init__(self, backend: str = "auto", model: Optional[str] = None,
                 api_key: Optional[str] = None, cache: bool = True):
        self.logger = logging.getLogger(__name__)
        self.backend = self._resolve_backend(backend)
        self.model = model or self.DEFAULT_MODELS[self.backend]
        self.api_key = api_key
        self.cache_enabled = cache
        self._cache: Dict[str, np.ndarray] = {}
        self._st_model = None  # lazily-loaded SentenceTransformer

        if self.backend == "openai" and api_key:
            openai.api_key = api_key

        self.logger.info(
            f"EmbeddingManager initialized (backend={self.backend}, model={self.model})"
        )

    def _resolve_backend(self, backend: str) -> str:
        """Pick a concrete backend, honoring an explicit request or auto-detecting."""
        if backend == "auto":
            if SENTENCE_TRANSFORMERS_AVAILABLE:
                return "sentence_transformers"
            if OPENAI_AVAILABLE:
                return "openai"
            return "hash"
        if backend == "sentence_transformers" and not SENTENCE_TRANSFORMERS_AVAILABLE:
            raise ImportError(
                "sentence-transformers not installed. "
                "Install with: pip install sentence-transformers"
            )
        if backend == "openai" and not OPENAI_AVAILABLE:
            raise ImportError("openai not installed. Install with: pip install openai")
        if backend not in self.DEFAULT_MODELS:
            raise ValueError(f"Unknown embedding backend: {backend}")
        return backend

    def _cache_key(self, text: str) -> str:
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return f"{self.backend}:{self.model}:{digest}"

    def generate_embedding(self, text: str) -> np.ndarray:
        """Return the embedding vector for a single piece of text."""
        if self.cache_enabled:
            key = self._cache_key(text)
            if key in self._cache:
                return self._cache[key]

        embedding = self._embed_one(text)

        if self.cache_enabled:
            self._cache[self._cache_key(text)] = embedding
        return embedding

    def batch_embed(self, texts: List[str]) -> List[np.ndarray]:
        """Embed a list of texts. Uses native batching where the backend supports it."""
        if not texts:
            return []

        # Fast path: serve everything from cache when possible.
        if self.cache_enabled:
            missing = [t for t in texts if self._cache_key(t) not in self._cache]
        else:
            missing = texts

        if missing:
            if self.backend == "sentence_transformers":
                vectors = self._embed_st(missing)
            elif self.backend == "openai":
                vectors = self._embed_openai(missing)
            else:
                vectors = [self._embed_hash(t) for t in missing]

            if self.cache_enabled:
                for t, v in zip(missing, vectors):
                    self._cache[self._cache_key(t)] = v

        if self.cache_enabled:
            return [self._cache[self._cache_key(t)] for t in texts]
        # No cache: re-map the freshly computed vectors back onto the input order.
        result, it = [], iter(vectors)
        for t in texts:
            result.append(next(it))
        return result

    def _embed_one(self, text: str) -> np.ndarray:
        if self.backend == "sentence_transformers":
            return self._embed_st([text])[0]
        if self.backend == "openai":
            return self._embed_openai([text])[0]
        return self._embed_hash(text)

    def _embed_st(self, texts: List[str]) -> List[np.ndarray]:
        if self._st_model is None:
            self._st_model = SentenceTransformer(self.model)
        arr = self._st_model.encode(texts, convert_to_numpy=True)
        return [np.asarray(v, dtype=np.float32) for v in arr]

    def _embed_openai(self, texts: List[str]) -> List[np.ndarray]:
        try:
            # openai>=1.0 client interface
            client = openai.OpenAI(api_key=self.api_key) if hasattr(openai, "OpenAI") else None
            if client is not None:
                resp = client.embeddings.create(model=self.model, input=texts)
                return [np.asarray(d.embedding, dtype=np.float32) for d in resp.data]
            # legacy openai<1.0 fallback
            resp = openai.Embedding.create(model=self.model, input=texts)
            return [np.asarray(d["embedding"], dtype=np.float32) for d in resp["data"]]
        except Exception as e:
            self.logger.error(f"OpenAI embedding failed: {e}")
            raise

    def _embed_hash(self, text: str) -> np.ndarray:
        """Deterministic, dependency-free embedding via token hashing.

        Not semantically meaningful like a learned model, but stable and fast —
        good enough for plumbing, offline use, and tests.
        """
        vec = np.zeros(self.HASH_DIM, dtype=np.float32)
        tokens = text.lower().split()
        if not tokens:
            return vec
        for tok in tokens:
            h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
            idx = h % self.HASH_DIM
            sign = 1.0 if (h >> 8) & 1 else -1.0
            vec[idx] += sign
        norm = np.linalg.norm(vec)
        return vec / norm if norm > 0 else vec

    def clear_cache(self):
        """Drop all cached embeddings."""
        self._cache.clear()
