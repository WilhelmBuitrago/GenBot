from __future__ import annotations

from fastapi import Request

from app.config import AppState
from app.core.settings import get_settings


def get_app_state(request: Request) -> AppState:
    return request.app.state.app_state


def get_conversation_memory(request: Request):
    return request.app.state.app_state.memory


def get_llm_client(request: Request):
    return request.app.state.app_state.llm_client


def get_app_settings():
    return get_settings()
