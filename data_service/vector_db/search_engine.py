"""
Search Engine
A query-friendly layer over VectorStore: accepts plain-text queries, embeds
them via EmbeddingManager, runs vector search, and offers optional lexical
reranking, metadata filtering, and hybrid (vector + keyword) scoring.
"""

import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

from .embedding_manager import EmbeddingManager
from .vector_store import VectorDocument, VectorStore


class SearchEngine:
    """High-level search over a VectorStore."""

    def __init__(self, vector_store: VectorStore,
                 embedding_manager: Optional[EmbeddingManager] = None):
        self.logger = logging.getLogger(__name__)
        self.vector_store = vector_store
        self.embedding_manager = embedding_manager or EmbeddingManager()

    def search(self, query: str, collection: str = "default", top_k: int = 10,
               similarity_threshold: float = 0.0,
               metadata_filter: Optional[Dict[str, Any]] = None
               ) -> List[Tuple[VectorDocument, float]]:
        """Embed the query, run vector search, and optionally filter by metadata."""
        query_embedding = self.embedding_manager.generate_embedding(query)
        # Over-fetch when filtering so the filter doesn't starve top_k.
        fetch_k = top_k * 3 if metadata_filter else top_k
        results = self.vector_store.search_similar(
            query_embedding, collection=collection, top_k=fetch_k,
            similarity_threshold=similarity_threshold,
        )
        if metadata_filter:
            results = [
                (doc, score) for doc, score in results
                if self._matches_filter(doc, metadata_filter)
            ]
        return results[:top_k]

    def rerank(self, query: str, results: List[Tuple[VectorDocument, float]],
               alpha: float = 0.5) -> List[Tuple[VectorDocument, float]]:
        """Blend the vector score with a lexical-overlap score.

        alpha weights the original (vector) score; (1 - alpha) weights lexical
        overlap between the query and each document's content. No extra deps.
        """
        if not results:
            return []
        query_terms = set(query.lower().split())
        if not query_terms:
            return results

        reranked = []
        for doc, score in results:
            doc_terms = set(doc.content.lower().split())
            overlap = len(query_terms & doc_terms) / len(query_terms)
            blended = alpha * score + (1 - alpha) * overlap
            reranked.append((doc, blended))
        reranked.sort(key=lambda x: x[1], reverse=True)
        return reranked

    def hybrid_search(self, query: str, collection: str = "default",
                      top_k: int = 10, alpha: float = 0.5,
                      metadata_filter: Optional[Dict[str, Any]] = None
                      ) -> List[Tuple[VectorDocument, float]]:
        """Vector search followed by lexical reranking, returning top_k."""
        # Pull a wider candidate set, then rerank and trim.
        candidates = self.search(
            query, collection=collection, top_k=top_k * 3,
            metadata_filter=metadata_filter,
        )
        return self.rerank(query, candidates, alpha=alpha)[:top_k]

    def _matches_filter(self, doc: VectorDocument,
                        metadata_filter: Dict[str, Any]) -> bool:
        """A document matches when every filter key equals (or its callable passes)."""
        for key, expected in metadata_filter.items():
            actual = doc.metadata.get(key)
            if isinstance(expected, Callable):
                if not expected(actual):
                    return False
            elif actual != expected:
                return False
        return True
