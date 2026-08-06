"""Application configuration.

Single-user for now. `OPERATOR_ID` is the one principal the app runs as; every
personal table carries it so that adding real multi-user later is a config
change rather than a migration of every row. See the plan, §6 "Data model rules".
"""

from __future__ import annotations

from functools import lru_cache
from uuid import UUID

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# The fixed singleton operator. Deliberately a real UUID rather than NULL so
# that personal rows are already scoped correctly the day a second user exists.
DEFAULT_OPERATOR_ID = UUID("00000000-0000-4000-8000-000000000001")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="LIGHTHOUSE_", extra="ignore")

    database_url: str = Field(
        default="postgresql+psycopg://localhost/lighthouse",
        validation_alias=AliasChoices("LIGHTHOUSE_DATABASE_URL", "DATABASE_URL"),
    )
    operator_id: UUID = DEFAULT_OPERATOR_ID

    supabase_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("LIGHTHOUSE_SUPABASE_URL", "NEXT_PUBLIC_SUPABASE_URL"),
    )
    supabase_publishable_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "LIGHTHOUSE_SUPABASE_PUBLISHABLE_KEY",
            "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY",
            "NEXT_PUBLIC_SUPABASE_ANON_KEY",
        ),
    )
    supabase_secret_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "LIGHTHOUSE_SUPABASE_SECRET_KEY", "SUPABASE_SERVICE_ROLE_KEY", "SECRET_KEY"
        ),
    )

    @field_validator("database_url")
    @classmethod
    def _use_psycopg_driver(cls, value: str) -> str:
        """Supabase hands out a bare ``postgresql://`` URI; SQLAlchemy needs the
        driver named. Anything that is not a URI at all is rejected here rather
        than at first query, where the error is a connection timeout with no
        indication that the setting is malformed."""
        if "://" not in value:
            raise ValueError(
                f"database_url must be a connection URI, got {value!r}. "
                "Supabase's Connect dialog gives the full string under "
                "'Direct · Connection string' -> Session pooler."
            )
        scheme, rest = value.split("://", 1)
        if scheme in {"postgres", "postgresql"}:
            return f"postgresql+psycopg://{rest}"
        return value

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
