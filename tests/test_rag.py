"""
Comprehensive Test Suite for RAG Pipeline.
Verifies chunking, embedding generation, vector store operations,
similarity ranking, and multi-tenant isolation.
"""

import os
import shutil
import asyncio
import tempfile
import numpy as np

from rag_core.chunker import RecursiveCharacterChunker, DocumentChunk
from rag_core.document_loader import DocumentLoader
from rag_core.embeddings import EmbeddingEngine
from rag_core.vector_store import VectorStore
from rag_core.rag_service import RAGService


class TestRAGPipeline:

    def test_recursive_chunker(self):
        chunker = RecursiveCharacterChunker(chunk_size=100, chunk_overlap=20)
        sample_text = (
            "The Discord server was founded in 2024. "
            "Members can participate in weekly gaming tournaments every Friday. "
            "Please ensure you follow the anti-spam guidelines in #rules. "
            "Violation of guidelines results in an automated timeout or warning."
        )
        chunks = chunker.split_text(sample_text, metadata={"source": "faq.txt", "guild_id": 123})

        assert len(chunks) >= 2
        for chunk in chunks:
            assert len(chunk.content) <= 120
            assert chunk.metadata["source"] == "faq.txt"
            assert chunk.metadata["guild_id"] == 123
            assert chunk.chunk_id is not None

    def test_document_loader_text(self):
        content = b"Rule 1: Be respectful.\nRule 2: No advertisement."
        docs = DocumentLoader.load_file_bytes(content, "rules.md", {"guild_id": 999})
        assert len(docs) == 1
        assert "Rule 1: Be respectful." in docs[0].content
        assert docs[0].metadata["source"] == "rules.md"

    def test_embedding_fallback_and_normalization(self):
        async def _run():
            engine = EmbeddingEngine(api_key="")  # Force local deterministic fallback
            assert not engine.is_cloud_active

            vec1 = await engine.get_embedding("Discord moderation rules and guidelines")
            vec2 = await engine.get_embedding("Gaming tournament schedule")
            vec3 = await engine.get_embedding("Rules for Discord moderators")

            # Check normalization
            norm1 = np.linalg.norm(np.array(vec1))
            assert abs(norm1 - 1.0) < 1e-4

            # Semantic check on fallback: vec1 should be closer to vec3 than to vec2
            sim_1_3 = np.dot(vec1, vec3)
            sim_1_2 = np.dot(vec1, vec2)
            assert sim_1_3 > sim_1_2

        asyncio.run(_run())

    def test_vector_store_persistence_and_search(self):
        temp_dir = tempfile.mkdtemp()
        try:
            store = VectorStore(storage_dir=temp_dir)

            # Create dummy chunks with known orthogonal vectors
            c1 = DocumentChunk(
                chunk_id="chunk_1",
                content="Information about weekly Minecraft events.",
                metadata={"source": "events.txt", "guild_id": 111},
                embedding=[1.0, 0.0, 0.0],
            )
            c2 = DocumentChunk(
                chunk_id="chunk_2",
                content="Discord server moderation commands list.",
                metadata={"source": "mod.txt", "guild_id": 111},
                embedding=[0.0, 1.0, 0.0],
            )
            c3 = DocumentChunk(
                chunk_id="chunk_3",
                content="Secret guild 222 announcement.",
                metadata={"source": "secret.txt", "guild_id": 222},
                embedding=[1.0, 0.0, 0.0],
            )

            store.add_chunks([c1, c2, c3])
            assert len(store.chunks) == 3

            # Search with vector [0.8, 0.6, 0.0] for guild 111 (score for c1=0.8, score for c2=0.6)
            query_vec = [0.8, 0.6, 0.0]
            results = store.search(query_vec, top_k=2, min_score=0.1, guild_id=111)

            assert len(results) == 2
            top_chunk, top_score = results[0]
            assert top_chunk.chunk_id == "chunk_1"
            assert top_score >= 0.79

            # Multi-tenant check: chunk_3 from guild 222 must NOT appear for guild 111
            assert not any(c.metadata["guild_id"] == 222 for c, _ in results)

            # Test reload from disk
            reloaded_store = VectorStore(storage_dir=temp_dir)
            assert len(reloaded_store.chunks) == 3
            reloaded_results = reloaded_store.search(query_vec, top_k=1, guild_id=111)
            assert reloaded_results[0][0].chunk_id == "chunk_1"

            # Test delete source
            reloaded_store.delete_source("events.txt", guild_id=111)
            stats = reloaded_store.get_stats(guild_id=111)
            assert stats["total_chunks"] == 1
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_end_to_end_rag_service(self):
        async def _run():
            temp_dir = tempfile.mkdtemp()
            try:
                service = RAGService()
                service.vector_store = VectorStore(storage_dir=temp_dir)

                # Ingest FAQ text
                faq_text = (
                    "The server invite link is https://discord.gg/example.\n"
                    "To get the VIP role, a member must reach Level 10 in chat XP.\n"
                    "Server giveaways are hosted every Sunday at 6 PM EST."
                )
                count = await service.ingest_text(faq_text, source_name="faq.md", guild_id=555)
                assert count >= 1

                # Test search
                matches = await service.search("How do I get the VIP role?", guild_id=555, top_k=1)
                assert len(matches) > 0
                best_chunk, score = matches[0]
                assert "VIP role" in best_chunk.content

                # Test diagnostics
                stats = service.get_stats(guild_id=555)
                assert stats["total_chunks"] >= 1
                assert "faq.md" in stats["sources"]
            finally:
                shutil.rmtree(temp_dir, ignore_errors=True)

        asyncio.run(_run())
