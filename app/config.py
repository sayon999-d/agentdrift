"""Central configuration. Compatible with python-dotenv + pydantic-settings."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    HOST: str = "127.0.0.1"
    PORT: int = 8901
    LOG_LEVEL: str = "info"
    ENV: str = "dev"

    DATABASE_URL: str = ""
    SUPABASE_DB_URL: str = ""
    SYNC_DATABASE_URL: str = ""

    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"
    EMBEDDING_DIM: int = 384
    EMBEDDING_FALLBACK_HASH: bool = True
    NLI_MODEL: str = "cross-encoder/nli-deberta-v3-small"
    NLI_ENABLED: bool = False

    DRIFT_SIMILARITY_THRESHOLD: float = 0.85
    DRIFT_AUTO_DETECT: bool = True

    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    @property
    def async_db_url(self) -> str:
        url = self.DATABASE_URL or self.SUPABASE_DB_URL
        if not url:
            return ""
        # Normalize to asyncpg driver
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        if "+asyncpg" not in url and url.startswith("postgresql"):
            # e.g. already has +psycopg
            pass
        return url

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
