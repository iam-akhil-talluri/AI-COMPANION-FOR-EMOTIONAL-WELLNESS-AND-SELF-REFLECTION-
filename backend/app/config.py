from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    # OpenAI secret key. Read from backend/.env only; never sent to the frontend.
    openai_api_key: str
    openai_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"

    # RAG settings
    knowledge_base_path: Path = BACKEND_DIR / "data" / "knowledge_base.json"
    rag_index_path: Path = BACKEND_DIR / "data" / "rag_index.json"
    rag_top_k: int = 3
    # Passages scoring below this cosine similarity are not given to the model.
    rag_min_score: float = 0.30

    cors_origins: str = "http://localhost:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
