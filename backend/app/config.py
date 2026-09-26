"""Único lugar que lê secrets/env. Nada aqui é serializado para prompts."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

APP_DIR = Path(__file__).resolve().parent
REPO_ROOT = APP_DIR.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", env_file_encoding="utf-8", extra="ignore")

    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    llm_timeout_seconds: float = 60.0
    llm_fallback_enabled: bool = False

    demo_mode: bool = True
    frontend_dist: Path = REPO_ROOT / "frontend" / "dist"

    mock_data_dir: Path = APP_DIR / "data" / "mock"
    knowledge_corpus_dir: Path = APP_DIR / "knowledge" / "corpus"
    governance_dir: Path = APP_DIR / "governance"
    agent_cards_dir: Path = APP_DIR / "agents" / "cards"

    @property
    def llm_configured(self) -> bool:
        return bool(self.llm_api_key)

    def secret_values(self) -> list[str]:
        """Valores que o Output Guard e o provider usam para garantir que nenhum secret vaza."""
        return [v for v in (self.llm_api_key,) if v]


@lru_cache
def get_settings() -> Settings:
    return Settings()
