"""
Text Chunking Module for RAG Engine.
Implements recursive character-based text splitting with overlap to preserve semantic context.
"""

from dataclasses import dataclass, field
import hashlib
import re
import time
from typing import List, Dict, Any, Optional


@dataclass
class DocumentChunk:
    chunk_id: str
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    embedding: Optional[List[float]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "content": self.content,
            "metadata": self.metadata,
            "embedding": self.embedding,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DocumentChunk":
        return cls(
            chunk_id=data["chunk_id"],
            content=data["content"],
            metadata=data.get("metadata", {}),
            embedding=data.get("embedding"),
        )


class RecursiveCharacterChunker:
    """
    Recursively splits text into semantically cohesive chunks using hierarchical separators.
    Preserves context by maintaining sliding-window overlap between chunks.
    """

    def __init__(
        self,
        chunk_size: int = 500,
        chunk_overlap: int = 80,
        separators: Optional[List[str]] = None,
    ):
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")

        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = separators or ["\n\n", "\n", ". ", "? ", "! ", "; ", " ", ""]

    def _split_text_with_separator(self, text: str, separator: str) -> List[str]:
        if separator:
            parts = text.split(separator)
            # Reattach the separator to preserve sentence boundaries where appropriate
            if separator in (". ", "? ", "! "):
                results = []
                for i, part in enumerate(parts):
                    if i < len(parts) - 1:
                        results.append(part + separator.strip())
                    elif part:
                        results.append(part)
                return [p for p in results if p.strip()]
            return [p for p in parts if p.strip()]
        return list(text)

    def _recursive_split(self, text: str, separators: List[str]) -> List[str]:
        final_chunks: List[str] = []
        separator = separators[-1]
        new_separators = []

        for i, sep in enumerate(separators):
            if sep == "":
                separator = ""
                break
            if sep in text:
                separator = sep
                new_separators = separators[i + 1:]
                break

        splits = self._split_text_with_separator(text, separator)
        good_splits: List[str] = []

        for split in splits:
            if len(split) < self.chunk_size:
                good_splits.append(split)
            else:
                if new_separators:
                    sub_splits = self._recursive_split(split, new_separators)
                    good_splits.extend(sub_splits)
                else:
                    good_splits.append(split)

        # Merge splits up to chunk_size with chunk_overlap
        current_chunk: List[str] = []
        current_len = 0

        for split in good_splits:
            split_len = len(split)
            if current_len + split_len + (len(separator) if current_chunk else 0) <= self.chunk_size:
                current_chunk.append(split)
                current_len += split_len + (len(separator) if len(current_chunk) > 1 else 0)
            else:
                if current_chunk:
                    joined = separator.join(current_chunk).strip()
                    if joined:
                        final_chunks.append(joined)
                    
                    # Compute overlap buffer from trailing items
                    overlap_chunk = []
                    overlap_len = 0
                    for item in reversed(current_chunk):
                        if overlap_len + len(item) <= self.chunk_overlap:
                            overlap_chunk.insert(0, item)
                            overlap_len += len(item)
                        else:
                            break
                    current_chunk = overlap_chunk
                    current_len = overlap_len

                current_chunk.append(split)
                current_len += split_len

        if current_chunk:
            joined = separator.join(current_chunk).strip()
            if joined:
                final_chunks.append(joined)

        return final_chunks

    def split_text(self, text: str, metadata: Optional[Dict[str, Any]] = None) -> List[DocumentChunk]:
        """Splits raw text into DocumentChunks with attached metadata."""
        cleaned = re.sub(r"\r\n?", "\n", text).strip()
        if not cleaned:
            return []

        raw_chunks = self._recursive_split(cleaned, self.separators)
        meta = metadata.copy() if metadata else {}
        source = meta.get("source", "unnamed_source")
        total = len(raw_chunks)
        chunks: List[DocumentChunk] = []

        for i, text_block in enumerate(raw_chunks):
            # Unique deterministic ID based on content hash and index
            content_hash = hashlib.sha256(f"{source}_{i}_{text_block}".encode("utf-8")).hexdigest()[:12]
            chunk_meta = {
                **meta,
                "chunk_index": i + 1,
                "total_chunks": total,
                "char_count": len(text_block),
                "created_at": time.time(),
            }
            chunks.append(
                DocumentChunk(
                    chunk_id=f"{content_hash}_{i+1}",
                    content=text_block,
                    metadata=chunk_meta,
                )
            )

        return chunks
