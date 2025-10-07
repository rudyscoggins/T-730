"""Fallback stub for discord.py when native dependencies are unavailable.

This stub implements just enough of the public surface that our unit tests
exercise so that importing :mod:`bot.main` does not crash in environments where
``discord`` (and its transitive dependencies like ``aiohttp``) cannot be loaded
because of missing shared libraries.  At runtime inside the actual container we
still expect the real package to be present; this module is only used as a
fallback during testing.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Optional


class Intents:
    """Minimal stand-in for :class:`discord.Intents`."""

    def __init__(self) -> None:
        self.message_content: bool = False

    @classmethod
    def default(cls) -> "Intents":
        return cls()


class _Loop:
    """Small helper that mimics the interface used in ``bot.main``."""

    def create_task(self, coro: Awaitable[Any]) -> asyncio.Task[Any]:
        return asyncio.create_task(coro)


class Client:
    """Very small stub of :class:`discord.Client` used in tests."""

    def __init__(self, *, intents: Optional[Intents] = None) -> None:
        self.intents = intents
        self.loop = _Loop()
        self._ready = False
        self._events: dict[str, Callable[..., Any]] = {}
        self.user = "discord-stub"

    def event(self, func: Callable[..., Any]) -> Callable[..., Any]:
        self._events[func.__name__] = func
        return func

    def is_ready(self) -> bool:
        return self._ready

    def get_channel(self, channel_id: int) -> None:  # pragma: no cover - unused
        return None

    async def fetch_channel(self, channel_id: int) -> None:  # pragma: no cover - unused
        return None

    async def start(self, token: str) -> None:  # pragma: no cover - unused
        self._ready = True

    def run(self, token: str) -> None:  # pragma: no cover - unused
        self._ready = True


class _Author:
    def __init__(self, bot: bool = False) -> None:
        self.bot = bot


class _Channel:
    def __init__(self, channel_id: int = 0) -> None:
        self.id = channel_id


class Message:
    """Minimal stand-in for :class:`discord.Message`.

    Only the attributes and methods accessed by our bot are provided.
    """

    def __init__(self, content: str = "", channel_id: int = 0, author_is_bot: bool = False) -> None:  # pragma: no cover - helper for tests only
        self.content = content
        self.channel = _Channel(channel_id)
        self.author = _Author(author_is_bot)

    async def add_reaction(self, _emoji: str) -> None:  # pragma: no cover - noop in stub
        return None

    async def reply(self, _content: str) -> None:  # pragma: no cover - noop in stub
        return None


__all__ = ["Client", "Intents", "Message"]
