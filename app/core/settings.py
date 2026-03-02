from __future__ import annotations

import os
from functools import lru_cache
from typing import List, Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError

load_dotenv()


class Settings(BaseModel):
    app_name: str = "GenBot"
    environment: str = "local"
    cors_origins: List[str] = Field(default_factory=list)

    llm_provider: str = Field(..., min_length=1)
    llm_base_url: str = Field(..., min_length=1)
    llm_chat_path: str = "/chat/completions"
    llm_api_key: str = Field(..., min_length=1)
    llm_model: str = Field(..., min_length=1)
    llm_timeout_seconds: float = 15.0
    llm_referer: Optional[str] = None
    llm_title: Optional[str] = None

    memory_max_messages: int = Field(3, ge=1, le=10)
    data_dir: str = "data"


def _parse_cors_origins(value: str) -> List[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    raw = {
        "app_name": os.getenv("APP_NAME", "GenBot"),
        "environment": os.getenv("ENVIRONMENT", "local"),
        "cors_origins": _parse_cors_origins(os.getenv("CORS_ORIGINS", "")),
        "llm_provider": os.getenv("LLM_PROVIDER", ""),
        "llm_base_url": os.getenv("LLM_BASE_URL", ""),
        "llm_chat_path": os.getenv("LLM_CHAT_PATH", "/chat/completions"),
        "llm_api_key": os.getenv("LLM_API_KEY", ""),
        "llm_model": os.getenv("LLM_MODEL", ""),
        "llm_timeout_seconds": float(os.getenv("LLM_TIMEOUT_SECONDS", "15")),
        "llm_referer": os.getenv("LLM_REFERER"),
        "llm_title": os.getenv("LLM_TITLE"),
        "memory_max_messages": int(os.getenv("MEMORY_MAX_MESSAGES", "3")),
        "data_dir": os.getenv("DATA_DIR", "data"),
    }

    try:
        return Settings(**raw)
    except ValidationError as exc:
        raise RuntimeError(f"Invalid settings: {exc}") from exc
