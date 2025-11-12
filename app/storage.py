from __future__ import annotations
from typing import Any, Dict, Optional
from loguru import logger


class Storage:
    """Простое in-memory хранилище данных между шагами заявки."""

    def __init__(self):
        # {user_id: {"step": str, "data": dict}}
        self._sessions: Dict[int, Dict[str, Any]] = {}

    def start(self, user_id: int):
        self._sessions[user_id] = {"step": None, "data": {}}
        logger.debug(f"Начата новая сессия для {user_id}")

    def set_step(self, user_id: int, step: str):
        if user_id in self._sessions:
            self._sessions[user_id]["step"] = step
            logger.debug(f"[{user_id}] шаг -> {step}")

    def get_step(self, user_id: int) -> Optional[str]:
        return self._sessions.get(user_id, {}).get("step")

    def set_data(self, user_id: int, key: str, value: Any):
        if user_id not in self._sessions:
            self.start(user_id)
        self._sessions[user_id]["data"][key] = value
        logger.debug(f"[{user_id}] {key} = {value}")

    def get_data(self, user_id: int) -> Dict[str, Any]:
        return self._sessions.get(user_id, {}).get("data", {})

    def clear(self, user_id: int):
        if user_id in self._sessions:
            del self._sessions[user_id]
            logger.debug(f"[{user_id}] сессия очищена")