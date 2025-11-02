"""Configuration helpers for the T-730 bot."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from dotenv import load_dotenv

_DEFAULT_COOLDOWN_SECONDS = 30
_DEFAULT_MAX_VIDEO_DURATION_SECONDS = 10 * 60
_TRUTHY = {"1", "true", "yes", "on"}
_FALSY = {"0", "false", "no", "off"}


def _int_from_env(name: str) -> int | None:
    """Return an integer parsed from the environment or ``None`` when absent."""

    raw = os.getenv(name)
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        logging.warning("Environment variable %s=%r is not a valid integer", name, raw)
        return None


def _bool_from_env(name: str, *, default: bool) -> bool:
    """Return a boolean parsed from the environment with forgiving semantics."""

    raw = os.getenv(name)
    if raw is None:
        return default

    normalized = raw.strip().lower()
    if normalized in _TRUTHY:
        return True
    if normalized in _FALSY:
        return False

    logging.warning("Environment variable %s=%r is not a recognized boolean", name, raw)
    return default


@dataclass(frozen=True)
class BotConfig:
    """Immutable configuration values loaded from environment variables."""

    token: str | None
    channel_id: int | None
    guild_id: int | None
    playlist_id: str | None
    playlist_url: str | None
    max_video_duration_seconds: int
    cooldown_seconds: int
    health_host: str
    health_port: int

    @property
    def resolved_playlist_url(self) -> str | None:
        """Return a shareable playlist URL when available."""

        if self.playlist_url:
            return self.playlist_url
        if self.playlist_id:
            return f"https://youtube.com/playlist?list={self.playlist_id}"
        return None


def load_config() -> BotConfig:
    """Load configuration from the environment and provide sane defaults."""

    load_dotenv()

    token = os.getenv("DISCORD_TOKEN")
    channel_id = _int_from_env("CHANNEL_ID")
    guild_id = _int_from_env("GUILD_ID")
    playlist_id = os.getenv("PLAYLIST_ID")
    playlist_url = os.getenv("PLAYLIST_URL")

    max_video_duration = _int_from_env("MAX_VIDEO_DURATION_SECONDS")
    if not max_video_duration:
        max_video_duration = _DEFAULT_MAX_VIDEO_DURATION_SECONDS

    raw_cooldown = _int_from_env("ADDRADIO_COOLDOWN_SECONDS")
    if raw_cooldown is None:
        cooldown_seconds = _DEFAULT_COOLDOWN_SECONDS
    elif raw_cooldown < 0:
        logging.warning(
            "ADDRADIO_COOLDOWN_SECONDS=%s is negative; disabling cooldown",
            raw_cooldown,
        )
        cooldown_seconds = 0
    else:
        cooldown_seconds = raw_cooldown

    health_host = os.getenv("HEALTH_HOST", "0.0.0.0")
    health_port = _int_from_env("HEALTH_PORT") or 8081

    return BotConfig(
        token=token,
        channel_id=channel_id,
        guild_id=guild_id,
        playlist_id=playlist_id,
        playlist_url=playlist_url,
        max_video_duration_seconds=max_video_duration,
        cooldown_seconds=cooldown_seconds,
        health_host=health_host,
        health_port=health_port,
    )


__all__ = ["BotConfig", "load_config", "_bool_from_env", "_int_from_env"]
