"""Settings, read from the project's .env file (never sent to the browser)."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

PROJECT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_DIR / ".env")


@dataclass
class Settings:
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    chat_model: str = field(default_factory=lambda: os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini"))
    embedding_model: str = field(default_factory=lambda: os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"))

    # "local": OpenAI embeddings stored in embeddings/ + vector_db/
    # "openai_file_search": a hosted OpenAI vector store (File Search)
    vector_backend: str = field(default_factory=lambda: os.getenv("VECTOR_BACKEND", "local"))
    vector_store_id: str = field(default_factory=lambda: os.getenv("OPENAI_VECTOR_STORE_ID", ""))

    top_k: int = field(default_factory=lambda: int(os.getenv("TOP_K", "3")))
    # The two backends score on different scales (see README: Evaluation).
    local_min_score: float = field(default_factory=lambda: float(os.getenv("LOCAL_MIN_SCORE", "0.22")))
    file_search_min_score: float = field(default_factory=lambda: float(os.getenv("FILE_SEARCH_MIN_SCORE", "0.40")))

    max_chunk_chars: int = 800

    documents_dir: Path = PROJECT_DIR / "data" / "wellness_documents"
    embeddings_path: Path = PROJECT_DIR / "embeddings" / "embeddings.npy"
    index_path: Path = PROJECT_DIR / "vector_db" / "index.json"
    file_search_state_path: Path = PROJECT_DIR / "vector_db" / "file_search_store.json"

    def require_key(self) -> None:
        if not self.openai_api_key or self.openai_api_key.startswith("sk-your"):
            raise RuntimeError("OPENAI_API_KEY is missing: add it to the .env file in the project folder")


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
