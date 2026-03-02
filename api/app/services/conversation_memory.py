from __future__ import annotations

from collections import deque
from typing import Deque, Dict, List


class ConversationMemory:
    def __init__(self, max_messages: int = 4) -> None:
        self._max_messages = max_messages
        self._storage: Dict[str, Deque[dict]] = {}
        self._explicit_storage: Dict[str, Deque[dict]] = {}

    def add_message(self, user_id: str, role: str, content: str) -> None:
        history = self._storage.get(user_id)
        if history is None:
            history = deque(maxlen=self._max_messages)
            self._storage[user_id] = history
        history.append({"role": role, "content": content})

    def get_history(self, user_id: str) -> List[dict]:
        history = self._storage.get(user_id)
        if not history:
            return []
        return list(history)

    def add_explicit_fields(self, user_id: str, fields: dict) -> None:
        history = self._explicit_storage.get(user_id)
        if history is None:
            history = deque(maxlen=self._max_messages)
            self._explicit_storage[user_id] = history
        history.append(fields)

    def get_recent_explicit_fields(self, user_id: str) -> dict:
        history = self._explicit_storage.get(user_id)
        if not history:
            return {}

        resolved = {"service_name": None, "region": None, "mission": None}
        for item in reversed(history):
            for key in resolved:
                if resolved[key] is None and item.get(key) is not None:
                    resolved[key] = item.get(key)
        return resolved
