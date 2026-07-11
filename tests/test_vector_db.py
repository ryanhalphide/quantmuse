import os
import tempfile
import unittest

import numpy as np

from data_service.vector_db import (
    VectorStore, VectorDocument, EmbeddingManager, DocumentProcessor, SearchEngine
)


class TestEmbeddingManager(unittest.TestCase):
    """The dependency-free 'hash' backend lets these run anywhere."""

    def setUp(self):
        self.em = EmbeddingManager(backend="hash")

    def test_generate_embedding_shape_and_determinism(self):
        v1 = self.em.generate_embedding("apple beats earnings")
        v2 = self.em.generate_embedding("apple beats earnings")
        self.assertEqual(v1.shape, (EmbeddingManager.HASH_DIM,))
        np.testing.assert_array_equal(v1, v2)  # deterministic

    def test_different_text_different_embedding(self):
        v1 = self.em.generate_embedding("bullish on tech")
        v2 = self.em.generate_embedding("bearish on energy")
        self.assertFalse(np.array_equal(v1, v2))

    def test_batch_embed_matches_single(self):
        texts = ["one two three", "four five six", "seven eight"]
        batch = self.em.batch_embed(texts)
        self.assertEqual(len(batch), 3)
        np.testing.assert_array_equal(batch[0], self.em.generate_embedding(texts[0]))

    def test_empty_text(self):
        v = self.em.generate_embedding("")
        self.assertEqual(v.shape, (EmbeddingManager.HASH_DIM,))
        self.assertEqual(float(np.linalg.norm(v)), 0.0)

    def test_unknown_backend_raises(self):
        with self.assertRaises(ValueError):
            EmbeddingManager(backend="does-not-exist")


class TestDocumentProcessor(unittest.TestCase):
    def setUp(self):
        self.dp = DocumentProcessor(EmbeddingManager(backend="hash"))

    def test_clean_text(self):
        self.assertEqual(self.dp.clean_text("  hello\n\tworld  "), "hello world")

    def test_chunk_text_overlap(self):
        text = " ".join(str(i) for i in range(100))
        chunks = self.dp.chunk_text(text, chunk_size=40, overlap=10)
        self.assertGreater(len(chunks), 1)
        # Each chunk has at most chunk_size words.
        self.assertTrue(all(len(c.split()) <= 40 for c in chunks))

    def test_chunk_text_short(self):
        chunks = self.dp.chunk_text("just a few words", chunk_size=500)
        self.assertEqual(chunks, ["just a few words"])

    def test_chunk_invalid_overlap(self):
        with self.assertRaises(ValueError):
            self.dp.chunk_text("a b c", chunk_size=2, overlap=2)

    def test_process_produces_documents(self):
        text = " ".join(["word"] * 1200)
        docs = self.dp.process(text, source="news", metadata={"ticker": "AAPL"},
                               chunk_size=500, overlap=50)
        self.assertGreater(len(docs), 1)
        self.assertTrue(all(isinstance(d, VectorDocument) for d in docs))
        self.assertEqual(docs[0].metadata["ticker"], "AAPL")
        self.assertEqual(docs[0].metadata["chunk_count"], len(docs))
        self.assertEqual(docs[0].source, "news")

    def test_process_empty(self):
        self.assertEqual(self.dp.process("   "), [])


class TestSearchEngineEndToEnd(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.store = VectorStore(db_path=self.tmp.name)
        self.em = EmbeddingManager(backend="hash")
        self.dp = DocumentProcessor(self.em)
        self.engine = SearchEngine(self.store, self.em)

    def tearDown(self):
        self.store.close()
        os.unlink(self.tmp.name)

    def test_ingest_and_search(self):
        corpus = {
            "doc_tech": "apple google microsoft semiconductor chips technology rally",
            "doc_energy": "oil gas crude energy barrel pipeline drilling",
            "doc_health": "pharma biotech drug trial fda approval health",
        }
        for src, text in corpus.items():
            docs = self.dp.process(text, source=src, doc_id_prefix=src)
            for d in docs:
                self.assertTrue(self.store.add_document(d, collection="news"))

        results = self.engine.search("technology chips rally", collection="news", top_k=3)
        self.assertGreater(len(results), 0)
        # The tech doc should rank first for a tech query.
        self.assertEqual(results[0][0].source, "doc_tech")

    def test_metadata_filter(self):
        d1 = self.dp.process("alpha beta gamma", source="a", metadata={"region": "us"},
                             doc_id_prefix="a")[0]
        d2 = self.dp.process("alpha beta gamma", source="b", metadata={"region": "eu"},
                             doc_id_prefix="b")[0]
        self.store.add_document(d1, collection="c")
        self.store.add_document(d2, collection="c")
        results = self.engine.search("alpha beta gamma", collection="c", top_k=10,
                                     metadata_filter={"region": "us"})
        self.assertTrue(all(doc.metadata["region"] == "us" for doc, _ in results))

    def test_hybrid_search_runs(self):
        docs = self.dp.process("momentum strategy outperforms in bull markets",
                               source="s", doc_id_prefix="s")
        for d in docs:
            self.store.add_document(d, collection="c")
        results = self.engine.hybrid_search("momentum bull", collection="c", top_k=5)
        self.assertGreaterEqual(len(results), 1)


if __name__ == "__main__":
    unittest.main()
