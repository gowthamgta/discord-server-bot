"""
Vector Store Module for RAG Engine.
Provides high-performance in-memory vector similarity search backed by NumPy,
with persistence to disk and multi-tenant guild isolation.
"""

import os
import json
import logging
import time
from typing import List, Dict, Any, Optional, Tuple
import numpy as np

from config import DATA_DIR
from rag_core.chunker import DocumentChunk

logger = logging.getLogger("RAG.VectorStore")


class VectorStore:
    """
    In-memory vector database with cosine similarity indexing and disk persistence.
    Maintains an embedding matrix and metadata registry.
    """

    def __init__(self, storage_dir: Optional[str] = None):
        self.storage_dir = storage_dir or os.path.join(DATA_DIR, "rag_store")
        os.makedirs(self.storage_dir, exist_ok=True)
        self.meta_file = os.path.join(self.storage_dir, "chunks_meta.json")
        self.vectors_file = os.path.join(self.storage_dir, "vectors.npz")

        self.chunks: List[DocumentChunk] = []
        self.matrix: Optional[np.ndarray] = None  # Shape (N, D)
        self._load()

    def _load(self):
        """Loads chunks and vector matrix from disk."""
        if not os.path.exists(self.meta_file) or not os.path.exists(self.vectors_file):
            self.chunks = []
            self.matrix = None
            return

        try:
            with open(self.meta_file, "r", encoding="utf-8") as f:
                raw_chunks = json.load(f)
            self.chunks = [DocumentChunk.from_dict(c) for c in raw_chunks]

            npz_data = np.load(self.vectors_file)
            self.matrix = npz_data["matrix"]

            if len(self.chunks) != self.matrix.shape[0]:
                logger.warning("Vector matrix length mismatch with metadata. Rebuilding state.")
                self.chunks = []
                self.matrix = None
            else:
                logger.info(f"Loaded {len(self.chunks)} chunks from vector store.")
        except Exception as e:
            logger.error(f"Failed to load vector store from disk: {e}")
            self.chunks = []
            self.matrix = None

    def _save(self):
        """Persists chunks and vector matrix to disk."""
        try:
            raw_chunks = [c.to_dict() for c in self.chunks]
            temp_meta = self.meta_file + ".tmp"
            with open(temp_meta, "w", encoding="utf-8") as f:
                json.dump(raw_chunks, f, ensure_ascii=False, indent=2)
            os.replace(temp_meta, self.meta_file)

            if self.matrix is not None and self.matrix.size > 0:
                temp_vec = self.vectors_file + ".tmp.npz"
                np.savez_compressed(temp_vec, matrix=self.matrix)
                os.replace(temp_vec, self.vectors_file)
            elif os.path.exists(self.vectors_file):
                os.remove(self.vectors_file)
        except Exception as e:
            logger.error(f"Failed to save vector store: {e}")

    def add_chunks(self, new_chunks: List[DocumentChunk]):
        """Inserts or updates chunks and updates the vector matrix."""
        if not new_chunks:
            return

        valid_chunks = [c for c in new_chunks if c.embedding is not None and len(c.embedding) > 0]
        if not valid_chunks:
            logger.warning("No chunks with valid embeddings provided to add_chunks.")
            return

        new_vectors = np.array([c.embedding for c in valid_chunks], dtype=np.float32)

        # Normalize rows to unit length for cosine similarity
        norms = np.linalg.norm(new_vectors, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        new_vectors = new_vectors / norms

        # Remove any existing chunks with the same chunk_id
        new_ids = {c.chunk_id for c in valid_chunks}
        keep_indices = []
        for i, c in enumerate(self.chunks):
            if c.chunk_id not in new_ids:
                keep_indices.append(i)

        if len(keep_indices) < len(self.chunks) and self.matrix is not None:
            self.chunks = [self.chunks[i] for i in keep_indices]
            self.matrix = self.matrix[keep_indices]

        # Append
        self.chunks.extend(valid_chunks)
        if self.matrix is None or self.matrix.size == 0:
            self.matrix = new_vectors
        else:
            if self.matrix.shape[1] != new_vectors.shape[1]:
                logger.warning(
                    f"Dimension mismatch: existing {self.matrix.shape[1]}, new {new_vectors.shape[1]}. Resetting store to new dimensions."
                )
                self.chunks = valid_chunks
                self.matrix = new_vectors
            else:
                self.matrix = np.vstack([self.matrix, new_vectors])

        self._save()
        logger.info(f"VectorStore: added {len(valid_chunks)} chunks. Total chunks: {len(self.chunks)}.")

    def search(
        self,
        query_vector: List[float],
        top_k: int = 4,
        min_score: float = 0.30,
        guild_id: Optional[int] = None,
        source_filter: Optional[str] = None,
    ) -> List[Tuple[DocumentChunk, float]]:
        """
        Executes fast cosine similarity search across indexed chunks.
        Returns sorted list of (chunk, similarity_score).
        """
        if self.matrix is None or len(self.chunks) == 0 or not query_vector:
            return []

        q_vec = np.array(query_vector, dtype=np.float32)
        q_norm = np.linalg.norm(q_vec)
        if q_norm > 0:
            q_vec = q_vec / q_norm

        # Matrix-vector dot product yields cosine similarities
        scores = np.dot(self.matrix, q_vec)

        results: List[Tuple[DocumentChunk, float]] = []
        for i, score in enumerate(scores):
            chunk = self.chunks[i]
            meta = chunk.metadata

            # Guild isolation check (if guild_id is provided)
            if guild_id is not None:
                chunk_guild = meta.get("guild_id")
                # Accept if chunk has matching guild_id or is marked global
                if chunk_guild is not None and chunk_guild != guild_id:
                    continue

            # Source name filter
            if source_filter and meta.get("source") != source_filter:
                continue

            if float(score) >= min_score:
                results.append((chunk, float(score)))

        # Sort descending by similarity score
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    def delete_source(self, source: str, guild_id: Optional[int] = None) -> int:
        """Deletes all chunks belonging to a particular document source."""
        if not self.chunks:
            return 0

        keep_indices = []
        deleted_count = 0

        for i, c in enumerate(self.chunks):
            match_source = c.metadata.get("source") == source
            match_guild = guild_id is None or c.metadata.get("guild_id") == guild_id
            if match_source and match_guild:
                deleted_count += 1
            else:
                keep_indices.append(i)

        if deleted_count > 0:
            self.chunks = [self.chunks[i] for i in keep_indices]
            if keep_indices and self.matrix is not None:
                self.matrix = self.matrix[keep_indices]
            else:
                self.matrix = None
            self._save()

        return deleted_count

    def clear(self, guild_id: Optional[int] = None) -> int:
        """Clears vectors, either for a specific guild or globally."""
        if guild_id is None:
            count = len(self.chunks)
            self.chunks = []
            self.matrix = None
            self._save()
            return count

        keep_indices = []
        deleted_count = 0
        for i, c in enumerate(self.chunks):
            if c.metadata.get("guild_id") == guild_id:
                deleted_count += 1
            else:
                keep_indices.append(i)

        if deleted_count > 0:
            self.chunks = [self.chunks[i] for i in keep_indices]
            if keep_indices and self.matrix is not None:
                self.matrix = self.matrix[keep_indices]
            else:
                self.matrix = None
            self._save()

        return deleted_count

    def get_stats(self, guild_id: Optional[int] = None) -> Dict[str, Any]:
        """Provides diagnostic statistics about the vector store."""
        relevant_chunks = [
            c for c in self.chunks
            if guild_id is None or c.metadata.get("guild_id") in (guild_id, None)
        ]

        sources = {}
        for c in relevant_chunks:
            s = c.metadata.get("source", "unknown")
            sources[s] = sources.get(s, 0) + 1

        dim = self.matrix.shape[1] if self.matrix is not None and self.matrix.size > 0 else 0
        approx_kb = round((self.matrix.nbytes if self.matrix is not None else 0) / 1024, 2)

        return {
            "total_chunks": len(relevant_chunks),
            "unique_sources": len(sources),
            "sources": sources,
            "dimension": dim,
            "memory_kb": approx_kb,
        }
