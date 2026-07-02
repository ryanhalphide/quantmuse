"""
Document Processor
Turns raw text into VectorDocument objects ready for the VectorStore:
clean -> chunk -> embed -> wrap.
"""

import logging
import re
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from .embedding_manager import EmbeddingManager
from .vector_store import VectorDocument


class DocumentProcessor:
    """Prepare documents for ingestion into the vector store."""

    def __init__(self, embedding_manager: Optional[EmbeddingManager] = None):
        self.logger = logging.getLogger(__name__)
        self.embedding_manager = embedding_manager or EmbeddingManager()

    def clean_text(self, text: str) -> str:
        """Normalize whitespace and strip control characters."""
        if not text:
            return ""
        # Collapse runs of whitespace (incl. newlines/tabs) to single spaces.
        text = re.sub(r"\s+", " ", text)
        # Drop non-printable control chars.
        text = "".join(ch for ch in text if ch.isprintable() or ch == " ")
        return text.strip()

    def chunk_text(self, text: str, chunk_size: int = 500,
                   overlap: int = 50) -> List[str]:
        """Split text into word-based chunks with a sliding overlap.

        chunk_size and overlap are measured in words. overlap keeps context
        across chunk boundaries for better retrieval.
        """
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if overlap < 0 or overlap >= chunk_size:
            raise ValueError("overlap must be in [0, chunk_size)")

        words = text.split()
        if not words:
            return []
        if len(words) <= chunk_size:
            return [" ".join(words)]

        chunks, start = [], 0
        step = chunk_size - overlap
        while start < len(words):
            chunk = words[start:start + chunk_size]
            chunks.append(" ".join(chunk))
            if start + chunk_size >= len(words):
                break
            start += step
        return chunks

    def process(self, text: str, source: str = "unknown",
                metadata: Optional[Dict[str, Any]] = None,
                chunk_size: int = 500, overlap: int = 50,
                doc_id_prefix: Optional[str] = None) -> List[VectorDocument]:
        """Clean, chunk, embed and wrap text into VectorDocument objects.

        Returns one VectorDocument per chunk. Each carries chunk_index and
        chunk_count in its metadata so callers can reassemble or dedupe.
        """
        metadata = dict(metadata or {})
        cleaned = self.clean_text(text)
        if not cleaned:
            self.logger.warning("process() called with empty/blank text")
            return []

        chunks = self.chunk_text(cleaned, chunk_size=chunk_size, overlap=overlap)
        embeddings = self.embedding_manager.batch_embed(chunks)
        prefix = doc_id_prefix or uuid.uuid4().hex[:8]
        now = datetime.now()

        documents = []
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            chunk_meta = dict(metadata)
            chunk_meta.update({"chunk_index": i, "chunk_count": len(chunks)})
            documents.append(VectorDocument(
                id=f"{prefix}_{i}",
                content=chunk,
                metadata=chunk_meta,
                embedding=embedding,
                timestamp=now,
                source=source,
            ))
        self.logger.info(f"Processed '{source}' into {len(documents)} chunk(s)")
        return documents

    def process_and_store(self, vector_store, text: str, source: str = "unknown",
                          metadata: Optional[Dict[str, Any]] = None,
                          collection: str = "default", **chunk_kwargs) -> List[str]:
        """Convenience: process text and add every chunk to a VectorStore.

        Returns the list of document ids that were stored.
        """
        documents = self.process(text, source=source, metadata=metadata, **chunk_kwargs)
        stored = []
        for doc in documents:
            if vector_store.add_document(doc, collection=collection):
                stored.append(doc.id)
        return stored
