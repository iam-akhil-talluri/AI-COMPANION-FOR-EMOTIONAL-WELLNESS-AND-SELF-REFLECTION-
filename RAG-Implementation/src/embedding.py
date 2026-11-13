"""Turn text into vectors with the OpenAI embeddings API."""

import numpy as np
from openai import OpenAI

from .config import get_settings

_BATCH = 100
_client: OpenAI | None = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        settings = get_settings()
        settings.require_key()
        _client = OpenAI(api_key=settings.openai_api_key)
    return _client


class Embedder:
    def __init__(self, model: str | None = None):
        self.model = model or get_settings().embedding_model

    def embed(self, texts: list[str]) -> np.ndarray:
        """Return one L2-normalised row per text, so a dot product is cosine similarity."""
        if not texts:
            return np.zeros((0, 0), dtype=np.float32)
        rows: list[list[float]] = []
        for start in range(0, len(texts), _BATCH):
            resp = get_client().embeddings.create(model=self.model, input=texts[start:start + _BATCH])
            rows.extend(item.embedding for item in sorted(resp.data, key=lambda d: d.index))
        matrix = np.asarray(rows, dtype=np.float32)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        return matrix / np.where(norms == 0, 1, norms)

    def embed_one(self, text: str) -> np.ndarray:
        return self.embed([text])[0]
