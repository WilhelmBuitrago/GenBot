from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from app.models.schemas import Availability, Service
from app.services.conversation_memory import ConversationMemory
from app.services.llm_client import LLMClient


@dataclass
class AppState:
    services: List[Service]
    availability: Dict[str, Availability]
    memory: ConversationMemory
    llm_client: LLMClient
