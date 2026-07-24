"""Application configuration.

Single-user for now. `OPERATOR_ID` is the one principal the app runs as; every
personal table carries it so that adding real multi-user later is a config
change rather than a migration of every row. See the plan, §6 "Data model rules".
"""

from __future__ import annotations

from functools import lru_cache
from uuid import UUID

from pydantic_settings import BaseSettings, SettingsConfigDict

# The fixed singleton operator. Deliberately a real UUID rather than NULL so
# that personal rows are already scoped correctly the day a second user exists.
DEFAULT_OPERATOR_ID = UUID("00000000-0000-4000-8000-000000000001")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="LIGHTHOUSE_", extra="ignore")

    database_url: str = "postgresql+psycopg://localhost/lighthouse"
    operator_id: UUID = DEFAULT_OPERATOR_ID

    # LLM reasoning provider. "rule_based" needs no key and no network, and is
    # the fallback whenever a provider is unconfigured or over quota.
    llm_provider: str = "rule_based"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash-lite"

    # Local embedding model (384-dim, matches VECTOR(384) in the schema).
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dim: int = 384

    # Politeness for outbound fetches. Identifies the client to source hosts.
    user_agent: str = "lighthouse-jobsearch/0.1 (personal use)"
    http_timeout_seconds: float = 30.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
