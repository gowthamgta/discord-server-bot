"""
RAG Service Orchestrator.
Coordinates document ingestion, chunking, embedding generation, vector similarity search,
and LLM response synthesis with strict citation grounding.
"""

import logging
import time
from typing import List, Dict, Any, Optional, Tuple
import discord

from rag_core.document_loader import DocumentLoader, Document
from rag_core.chunker import RecursiveCharacterChunker, DocumentChunk
from rag_core.embeddings import EmbeddingEngine
from rag_core.vector_store import VectorStore
from rate_limiter import gemini_queue

logger = logging.getLogger("RAG.Service")


class RAGService:
    """
    Central orchestration service for the Retrieval-Augmented Generation pipeline.
    """

    def __init__(self):
        self.chunker = RecursiveCharacterChunker(chunk_size=550, chunk_overlap=90)
        self.embeddings = EmbeddingEngine()
        self.vector_store = VectorStore()

    async def ingest_text(
        self,
        text: str,
        source_name: str,
        guild_id: Optional[int] = None,
        extra_meta: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Chunks, embeds, and indexes arbitrary text."""
        doc_meta = {
            "source": source_name,
            "source_type": "text",
            "guild_id": guild_id,
            **(extra_meta or {}),
        }
        chunks = self.chunker.split_text(text, metadata=doc_meta)
        if not chunks:
            return 0

        # Generate embeddings in batch
        texts_to_embed = [c.content for c in chunks]
        vectors = await self.embeddings.get_embeddings_batch(texts_to_embed)

        for chunk, vec in zip(chunks, vectors):
            chunk.embedding = vec

        self.vector_store.add_chunks(chunks)
        return len(chunks)

    async def ingest_file(
        self,
        file_bytes: bytes,
        filename: str,
        guild_id: Optional[int] = None,
        extra_meta: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Parses a file from raw bytes, splits into chunks, embeds, and stores them."""
        doc_meta = {
            "source": filename,
            "guild_id": guild_id,
            **(extra_meta or {}),
        }
        docs = DocumentLoader.load_file_bytes(file_bytes, filename, doc_meta)
        if not docs:
            return 0

        all_chunks: List[DocumentChunk] = []
        for doc in docs:
            chunks = self.chunker.split_text(doc.content, metadata=doc.metadata)
            all_chunks.extend(chunks)

        if not all_chunks:
            return 0

        texts = [c.content for c in all_chunks]
        vectors = await self.embeddings.get_embeddings_batch(texts)
        for chunk, vec in zip(all_chunks, vectors):
            chunk.embedding = vec

        self.vector_store.add_chunks(all_chunks)
        return len(all_chunks)

    async def ingest_discord_channel(
        self,
        channel: discord.TextChannel,
        limit: int = 150,
        guild_id: Optional[int] = None,
    ) -> int:
        """
        Scrapes historical messages from a channel (e.g. #rules, #announcements, #faq),
        aggregates them into conversational context blocks, chunks, embeds, and stores them.
        """
        source_name = f"#{channel.name}"
        guild_id = guild_id or (channel.guild.id if channel.guild else None)

        messages = []
        try:
            async for m in channel.history(limit=limit, oldest_first=True):
                # Skip bot commands and empty spam
                if m.content.startswith(("/", "!", ".")) and len(m.content.split()) <= 2:
                    continue
                content = m.clean_content.strip()
                if content:
                    author_name = m.author.display_name
                    timestamp_str = m.created_at.strftime("%Y-%m-%d %H:%M")
                    messages.append(f"[{timestamp_str}] {author_name}: {content}")
        except Exception as e:
            logger.error(f"Failed to fetch channel history for #{channel.name}: {e}")
            raise

        if not messages:
            return 0

        full_text = "\n".join(messages)
        # First clear out old index for this channel to allow clean re-indexing
        self.vector_store.delete_source(source_name, guild_id=guild_id)

        meta = {
            "source": source_name,
            "source_type": "discord_channel",
            "channel_id": channel.id,
            "guild_id": guild_id,
            "channel_name": channel.name,
        }
        return await self.ingest_text(full_text, source_name, guild_id=guild_id, extra_meta=meta)

    async def search(
        self,
        query: str,
        guild_id: Optional[int] = None,
        top_k: int = 4,
        min_score: float = 0.30,
    ) -> List[Tuple[DocumentChunk, float]]:
        """Finds most semantically relevant chunks for a user query."""
        q_emb = await self.embeddings.get_embedding(query)
        if not q_emb:
            return []
        return self.vector_store.search(q_emb, top_k=top_k, min_score=min_score, guild_id=guild_id)

    async def answer_question(
        self,
        query: str,
        guild_id: Optional[int] = None,
        top_k: int = 4,
        min_score: float = 0.28,
        persona_instructions: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        End-to-end RAG query execution:
        1. Retrieval: Query embedding + vector similarity search.
        2. Filtering: Check relevance threshold.
        3. Context synthesis: Grounded prompt construction with source citations.
        4. Generation: LLM completion via rate-limited queue.
        """
        start_time = time.time()
        matches = await self.search(query, guild_id=guild_id, top_k=top_k, min_score=min_score)

        if not matches:
            return {
                "answer": (
                    "I searched the server knowledge base, but I couldn't find any relevant "
                    "documentation or discussions matching your question."
                ),
                "sources": [],
                "confidence": 0.0,
                "latency_ms": round((time.time() - start_time) * 1000, 1),
                "chunks_used": 0,
            }

        # Build context blocks
        context_blocks = []
        sources_meta = []
        seen_sources = set()

        for idx, (chunk, score) in enumerate(matches, 1):
            source = chunk.metadata.get("source", "Server Knowledge")
            page = chunk.metadata.get("page_number")
            source_label = f"{source} (Page {page})" if page else source
            confidence_pct = round(score * 100, 1)

            context_blocks.append(
                f"[Source {idx}: {source_label} | Relevance: {confidence_pct}%]\n{chunk.content}"
            )

            if source_label not in seen_sources:
                seen_sources.add(source_label)
                sources_meta.append({
                    "source": source_label,
                    "score": confidence_pct,
                    "excerpt": chunk.content[:200] + ("..." if len(chunk.content) > 200 else ""),
                })

        context_text = "\n\n---\n\n".join(context_blocks)

        prompt = (
            "You are an expert Discord Knowledge Assistant. Answer the user's question accurately using ONLY "
            "the provided excerpts from the server documentation and chat archives.\n\n"
            "Strict Guidelines:\n"
            "1. Grounding: Answer based strictly on the factual content provided in the excerpts.\n"
            "2. Honesty: If the excerpts do not contain enough information to fully answer, state what you know and "
            "honestly acknowledge what is missing.\n"
            "3. Citations: Reference the source names (e.g. `[#rules]` or `[FAQ.md]`) naturally when stating facts.\n"
            "4. Tone: Helpful, clear, concise, formatted with clean Discord markdown (bold, bullet points).\n"
            f"{persona_instructions or ''}\n\n"
            f"Context Excerpts:\n{context_text}\n\n"
            f"User Question: {query}\n\n"
            "Answer:"
        )

        try:
            raw_answer = await gemini_queue.ask_gemini(prompt)
            answer = raw_answer.strip() if raw_answer else "Sorry, I was unable to generate an answer at this time."
        except Exception as e:
            logger.error(f"Error generating RAG answer: {e}")
            answer = f"An error occurred while generating the response: {e}"

        avg_confidence = round(sum(m[1] for m in matches) / len(matches) * 100, 1)

        return {
            "answer": answer,
            "sources": sources_meta,
            "confidence": avg_confidence,
            "latency_ms": round((time.time() - start_time) * 1000, 1),
            "chunks_used": len(matches),
        }

    def delete_source(self, source: str, guild_id: Optional[int] = None) -> int:
        return self.vector_store.delete_source(source, guild_id=guild_id)

    def clear(self, guild_id: Optional[int] = None) -> int:
        return self.vector_store.clear(guild_id=guild_id)

    def get_stats(self, guild_id: Optional[int] = None) -> Dict[str, Any]:
        return self.vector_store.get_stats(guild_id=guild_id)


# Singleton instance
rag_service = RAGService()
