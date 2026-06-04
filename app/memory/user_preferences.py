from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class UserPreferenceStore:
    """
    Layer 2: User Preferences (Redis Hash per API key).
    Remembers coding style preferences across sessions.
    """

    def __init__(self, redis_client=None):
        self.redis = redis_client
        self.prefix = "user_pref:"
        self._available = redis_client is not None

    async def get_preferences(self, api_key: str) -> dict:
        if not self._available:
            return {}

        try:
            data = await self.redis.hgetall(f"{self.prefix}{api_key}")
            if not data:
                return {}
            return {k.decode(): v.decode() for k, v in data.items()}
        except Exception as e:
            logger.warning("get_preferences_failed", error=str(e))
            return {}

    async def update_from_request(
        self, api_key: str, request_data: dict
    ):
        if not self._available:
            return

        updates = {}
        if request_data.get("framework"):
            updates["preferred_framework"] = request_data["framework"]
        if request_data.get("language"):
            updates["preferred_language"] = request_data["language"]

        if updates:
            try:
                await self.redis.hset(
                    f"{self.prefix}{api_key}", mapping=updates
                )
            except Exception as e:
                logger.warning("update_preferences_failed", error=str(e))

    def build_preference_prompt(self, prefs: dict) -> str:
        if not prefs:
            return ""

        lines = ["用户的编码偏好（请遵循）："]
        for key, value in prefs.items():
            lines.append(f"  - {key}: {value}")
        return "\n".join(lines)
