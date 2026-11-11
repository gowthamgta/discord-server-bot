"""
Document Loader Module for RAG Engine.
Handles loading and extracting clean text and metadata from files (TXT, MD, PDF, JSON)
and Discord objects (channels, messages, attachments).
"""

import os
import json
import logging
from typing import Dict, Any, List, Optional
from io import BytesIO

logger = logging.getLogger("RAG.Loader")

try:
    import pypdf
    PYPDF_AVAILABLE = True
except ImportError:
    PYPDF_AVAILABLE = False


class Document:
    def __init__(self, content: str, metadata: Optional[Dict[str, Any]] = None):
        self.content = content.strip()
        self.metadata = metadata or {}

    def __repr__(self):
        return f"<Document source={self.metadata.get('source', 'unknown')} len={len(self.content)}>"


class DocumentLoader:
    """Extracts text and metadata from files or raw Discord data."""

    @staticmethod
    def load_text(text: str, source_name: str = "snippet", metadata: Optional[Dict[str, Any]] = None) -> Document:
        meta = metadata.copy() if metadata else {}
        meta.setdefault("source", source_name)
        meta.setdefault("source_type", "text")
        return Document(content=text, metadata=meta)

    @staticmethod
    def load_file_bytes(file_bytes: bytes, filename: str, metadata: Optional[Dict[str, Any]] = None) -> List[Document]:
        """Loads and parses file content from in-memory bytes."""
        meta = metadata.copy() if metadata else {}
        meta.setdefault("source", filename)
        lower_name = filename.lower()

        if lower_name.endswith(".pdf"):
            return DocumentLoader._load_pdf_bytes(file_bytes, meta)
        elif lower_name.endswith((".txt", ".md", ".markdown", ".csv", ".log", ".py", ".json")):
            return DocumentLoader._load_text_bytes(file_bytes, filename, meta)
        else:
            # Fallback to UTF-8 text decoding
            return DocumentLoader._load_text_bytes(file_bytes, filename, meta)

    @staticmethod
    def _load_text_bytes(file_bytes: bytes, filename: str, meta: Dict[str, Any]) -> List[Document]:
        try:
            text = file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            try:
                text = file_bytes.decode("latin-1")
            except Exception as e:
                logger.error(f"Failed to decode text file {filename}: {e}")
                return []

        meta["source_type"] = "file"
        meta["file_type"] = os.path.splitext(filename)[1].lstrip(".")
        return [Document(content=text, metadata=meta)]

    @staticmethod
    def _load_pdf_bytes(file_bytes: bytes, meta: Dict[str, Any]) -> List[Document]:
        if not PYPDF_AVAILABLE:
            logger.warning("pypdf is not installed. PDF parsing will be skipped.")
            return []

        docs = []
        try:
            reader = pypdf.PdfReader(BytesIO(file_bytes))
            for page_idx, page in enumerate(reader.pages):
                page_text = page.extract_text() or ""
                if page_text.strip():
                    page_meta = meta.copy()
                    page_meta["source_type"] = "pdf"
                    page_meta["page_number"] = page_idx + 1
                    page_meta["total_pages"] = len(reader.pages)
                    docs.append(Document(content=page_text, metadata=page_meta))
        except Exception as e:
            logger.error(f"Error parsing PDF: {e}")
        return docs

    @staticmethod
    def load_local_file(file_path: str, metadata: Optional[Dict[str, Any]] = None) -> List[Document]:
        """Reads a local disk file."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        filename = os.path.basename(file_path)
        with open(file_path, "rb") as f:
            content = f.read()
        return DocumentLoader.load_file_bytes(content, filename, metadata)
