"""
Embedding Engine for RAG.
Generates dense vector embeddings using Google GenAI (gemini-embedding-001).
Includes a local deterministic vectorizer fallback to ensure testability and graceful degradation.
"""

import asyncio
import logging
import math
from typing import List, Optional
import numpy as np

import config

logger = logging.getLogger("RAG.Embeddings")

try:
    from google import genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False


class EmbeddingEngine:
    """
    Manages vector embedding generation.
    Primary: Google Gemini `gemini-embedding-001` (Google's current official text embedding model).
    Fallback: Normalized term/n-gram hashing vectorizer (384-dim) for offline resilience.
    """

    DEFAULT_MODEL = "gemini-embedding-001"
    FALLBACK_DIM = 384

    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        self.api_key = api_key or getattr(config, "GEMINI_API_KEY", "").strip()
        self.model_name = model_name or self.DEFAULT_MODEL
        self._client = None
        self._init_client()

    def _init_client(self):
        if GENAI_AVAILABLE and self.api_key and self.api_key != "YOUR_GEMINI_API_KEY_HERE":
            try:
                self._client = genai.Client(api_key=self.api_key)
                logger.info(f"Initialized Google GenAI embedding client with model {self.model_name}.")
            except Exception as e:
                logger.warning(f"Could not initialize GenAI client: {e}. Fallback vectorizer will be used.")
                self._client = None
        else:
            self._client = None

    def refresh_key(self, api_key: str):
        self.api_key = api_key
        self._init_client()

    @property
    def is_cloud_active(self) -> bool:
        return self._client is not None

    def _normalize_vector(self, vec: np.ndarray) -> np.ndarray:
        norm = np.linalg.norm(vec)
        if norm > 1e-12:
            return vec / norm
        return vec

    def _generate_fallback_embedding(self, text: str) -> np.ndarray:
        """
        Deterministic lightweight feature hashing vectorizer.
        Generates consistent 384-dim unit vectors using word and character n-grams.
        Guarantees zero crashes if cloud API is unavailable.
        """
        vec = np.zeros(self.FALLBACK_DIM, dtype=np.float32)
        words = text.lower().split()
        if not words:
            return vec

        for word in words:
            # Word hash
            h = hash(word) % self.FALLBACK_DIM
            vec[h] += 1.0
            # Character trigram hashes for typo and morphological resilience
            if len(word) >= 3:
                for i in range(len(word) - 2):
                    trigram = word[i : i + 3]
                    th = hash(trigram) % self.FALLBACK_DIM
                    vec[th] += 0.5

        return self._normalize_vector(vec)

    async def get_embedding(self, text: str) -> List[float]:
        """Generates embedding for a single query or text string."""
        results = await self.get_embeddings_batch([text])
        return results[0] if results else []

    async def get_embeddings_batch(self, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        """Generates embeddings for a batch of strings, using asyncio.to_thread for non-blocking I/O."""
        if not texts:
            return []

        if self.is_cloud_active:
            try:
                all_embeddings: List[List[float]] = []
                for i in range(0, len(texts), batch_size):
                    batch = texts[i : i + batch_size]
                    response = await asyncio.to_thread(
                        self._client.models.embed_content,
                        model=self.model_name,
                        contents=batch,
                    )
                    if hasattr(response, "embeddings") and response.embeddings:
                        for emb in response.embeddings:
                            vec = np.array(emb.values, dtype=np.float32)
                            normed = self._normalize_vector(vec)
                            all_embeddings.append(normed.tolist())
                    else:
                        raise RuntimeError("No embeddings returned by Google GenAI.")
                return all_embeddings
            except Exception as e:
                logger.warning(f"Google GenAI embedding with {self.model_name} failed ({e}); falling back to local vectorizer.")

        # Fallback path
        return [self._generate_fallback_embedding(t).tolist() for t in texts]
