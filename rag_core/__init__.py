"""
RAG Engine Package for Discord Server Bot.
Provides modular document ingestion, recursive chunking, dense embeddings,
in-memory vector storage, and grounded generative retrieval.
"""

from rag_core.chunker import RecursiveCharacterChunker, DocumentChunk
from rag_core.embeddings import EmbeddingEngine
from rag_core.vector_store import VectorStore
from rag_core.document_loader import DocumentLoader, Document
from rag_core.rag_service import RAGService, rag_service

__all__ = [
    "RecursiveCharacterChunker",
    "DocumentChunk",
    "EmbeddingEngine",
    "VectorStore",
    "DocumentLoader",
    "Document",
    "RAGService",
    "rag_service",
]
