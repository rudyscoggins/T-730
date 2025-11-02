"""Utilities for tracking per-user cooldowns."""
from __future__ import annotations

import asyncio
import time
from typing import Dict


class CooldownTracker:
    """Track cooldown windows for users interacting with the bot."""

    def __init__(self, cooldown_seconds: int) -> None:
        self._cooldown_seconds = max(0, cooldown_seconds)
        self._timestamps: Dict[int, float] = {}
        self._lock = asyncio.Lock()

    @property
    def enabled(self) -> bool:
        """Return ``True`` when cooldown enforcement is active."""

        return self._cooldown_seconds > 0

    async def remaining(self, user_id: int, *, now: float | None = None) -> float:
        """Return the remaining cooldown for ``user_id`` in seconds."""

        if not self.enabled:
            return 0.0

        current = time.time() if now is None else now
        async with self._lock:
            last = self._timestamps.get(user_id)
            if last is None:
                return 0.0
            remaining = self._cooldown_seconds - (current - last)
        return remaining if remaining > 0 else 0.0

    async def mark(self, user_id: int, *, now: float | None = None) -> None:
        """Record the current time for ``user_id``'s cooldown window."""

        if not self.enabled:
            return

        current = time.time() if now is None else now
        async with self._lock:
            self._timestamps[user_id] = current


__all__ = ["CooldownTracker"]
