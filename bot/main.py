import os, logging, asyncio, time, math
from typing import Callable, TypeVar, Any

try:  # pragma: no cover - exercised indirectly via tests when discord missing
    import discord  # type: ignore
except Exception as exc:  # pragma: no cover - the fallback itself is tested
    logging.getLogger(__name__).warning(
        "discord import failed (%s); using lightweight stub", exc,
    )
    from . import discord_stub as discord  # type: ignore
from dotenv import load_dotenv
from .youtube import (
    add_to_playlist,
    video_exists,
    get_video_metadata,
)
from .youtube import CredentialsExpiredError
try:
    # discord.py depends on aiohttp; use it for an in-process health endpoint
    from aiohttp import web  # type: ignore
except Exception:  # pragma: no cover - only if aiohttp missing at runtime
    web = None  # type: ignore
from .youtube.urls import canonical_video_ids_from_text

_T = TypeVar("_T")

_FAST_RETRY_DELAY_SECONDS = 5
_FAST_RETRY_ATTEMPTS = 10
_SLOW_RETRY_DELAYS = (60, 300, 600)
_RETRY_WAIT_SECONDS: tuple[int, ...] = (
    (0,)
    + (_FAST_RETRY_DELAY_SECONDS,) * _FAST_RETRY_ATTEMPTS
    + _SLOW_RETRY_DELAYS
)
_NON_RETRYABLE_EXCEPTIONS = (CredentialsExpiredError,)


async def _call_with_retry(
    func: Callable[..., _T],
    *args: Any,
    description: str | None = None,
    **kwargs: Any,
) -> _T:
    """Execute ``func`` with exponential backoff style retries.

    Performs quick retries every 5 seconds for the first ten failures and then
    slows down to 1, 5, and 10 minute intervals before giving up.
    """

    desc = description or getattr(func, "__name__", "operation")
    total_attempts = len(_RETRY_WAIT_SECONDS)
    last_exc: BaseException | None = None

    for attempt, wait_seconds in enumerate(_RETRY_WAIT_SECONDS, start=1):
        if attempt > 1 and wait_seconds:
            logging.info(
                "Retrying %s in %s seconds (attempt %s/%s)",
                desc,
                wait_seconds,
                attempt,
                total_attempts,
            )
            await asyncio.sleep(wait_seconds)

        try:
            return await asyncio.to_thread(func, *args, **kwargs)
        except _NON_RETRYABLE_EXCEPTIONS:
            raise
        except Exception as exc:  # pragma: no cover - exercised via tests
            last_exc = exc
            if attempt == total_attempts:
                break
            logging.warning(
                "Attempt %s/%s for %s failed: %s",
                attempt,
                total_attempts,
                desc,
                exc,
            )

    assert last_exc is not None  # For mypy; we only exit loop on failure
    raise last_exc

# Best-effort detection of Discord HTTP errors without tightly coupling to discord.py
def _is_unknown_interaction_error(exc: Exception) -> bool:
    """Return True if the exception looks like a 10062 Unknown interaction error.

    Works across discord.py versions by checking common attributes and message text.
    """
    try:
        # discord.NotFound or HTTPException often carry .code or .status
        code = getattr(exc, "code", None)
        status = getattr(getattr(exc, "response", None), "status", None) or getattr(exc, "status", None)
        message = str(exc)
        if code == 10062:
            return True
        if (status == 404) and ("Unknown interaction" in message or "10062" in message):
            return True
        # Some variants embed json with code/message
        if "Unknown interaction" in message:
            return True
    except Exception:
        pass
    return False

async def _safe_followup_send(
    interaction,
    content: str | None = None,
    *,
    ephemeral: bool = True,
    embed=None,
):
    """Attempt to reply to an interaction while hiding Discord's thinking state."""

    try:
        if getattr(interaction, "response", None) and interaction.response.is_done():
            try:
                if embed is not None:
                    await interaction.edit_original_response(content=content, embed=embed)
                else:
                    await interaction.edit_original_response(content=content)
                return
            except Exception:
                logging.debug("edit_original_response failed; will try followup", exc_info=True)

        if getattr(interaction, "response", None) and not interaction.response.is_done():
            if embed is not None:
                await interaction.response.send_message(
                    content=content,
                    ephemeral=ephemeral,
                    embed=embed,
                )
            else:
                await interaction.response.send_message(content, ephemeral=ephemeral)
            return

        if embed is not None:
            await interaction.followup.send(content=content, ephemeral=ephemeral, embed=embed)
        else:
            await interaction.followup.send(content, ephemeral=ephemeral)
    except Exception as exc:
        if _is_unknown_interaction_error(exc):
            logging.debug("Interaction response token expired; falling back to channel")
            try:
                ch = await _resolve_channel_for_interaction(interaction)
                if ch is not None:
                    if embed is not None:
                        await ch.send(content=content, embed=embed)
                    else:
                        await ch.send(content or "")
                    return
            except Exception:
                logging.debug("Channel fallback after Unknown interaction failed", exc_info=True)
            return
        raise

load_dotenv()  # grabs .env mounted by compose


def _int_from_env(name: str) -> int | None:
    """Parse an integer environment variable, returning ``None`` if unset or invalid."""

    raw = os.getenv(name)
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        logging.warning("Environment variable %s=%r is not a valid integer", name, raw)
        return None


def _bool_from_env(name: str, *, default: bool) -> bool:
    """Return a boolean parsed from the environment, accepting common truthy strings."""

    raw = os.getenv(name)
    if raw is None:
        return default

    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False

    logging.warning("Environment variable %s=%r is not a recognized boolean", name, raw)
    return default


TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = _int_from_env("CHANNEL_ID")
GUILD_ID = _int_from_env("GUILD_ID")
PLAYLIST = os.getenv("PLAYLIST_ID")


def _resolve_playlist_url() -> str | None:
    """Return a shareable playlist URL if available."""

    explicit = os.getenv("PLAYLIST_URL")
    if explicit:
        return explicit
    if PLAYLIST:
        return f"https://youtube.com/playlist?list={PLAYLIST}"
    return None

logging.basicConfig(level=logging.INFO)
intents = discord.Intents.default()
bot = discord.Client(intents=intents)
 
# Slash commands (discord.app_commands) if available
app_commands = getattr(discord, "app_commands", None)
tree = app_commands.CommandTree(bot) if app_commands else None

START_TIME = time.time()
_health_started = False
MAX_VIDEO_DURATION_SECONDS = 10 * 60
_DEFAULT_ADDRADIO_COOLDOWN_SECONDS = 30

_configured_cooldown = _int_from_env("ADDRADIO_COOLDOWN_SECONDS")
if _configured_cooldown is None:
    ADDRADIO_COOLDOWN_SECONDS = _DEFAULT_ADDRADIO_COOLDOWN_SECONDS
elif _configured_cooldown < 0:
    logging.warning(
        "ADDRADIO_COOLDOWN_SECONDS=%s is negative; disabling cooldown",
        _configured_cooldown,
    )
    ADDRADIO_COOLDOWN_SECONDS = 0
else:
    ADDRADIO_COOLDOWN_SECONDS = _configured_cooldown

_user_cooldowns: dict[int, float] = {}
_user_cooldown_lock = asyncio.Lock()


def _format_duration(total_seconds: int) -> str:
    h, rem = divmod(max(0, int(total_seconds)), 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02}:{s:02}"
    return f"{m}:{s:02}"


def _build_video_embed(meta: dict):
    """Return a discord.Embed for the added video, or None if unsupported."""
    Embed = getattr(discord, "Embed", None)
    if Embed is None:
        return None
    title = meta.get("title") or meta.get("id")
    url = meta.get("url")
    channel = meta.get("channel_title") or ""
    duration_s = int(meta.get("duration_seconds") or 0)
    duration = _format_duration(duration_s)
    embed = Embed(title=title, url=url, color=0x2ecc71)
    if channel:
        embed.set_author(name=channel)
    embed.add_field(name="Duration", value=duration, inline=True)
    thumb = meta.get("thumbnail_url")
    if thumb:
        embed.set_thumbnail(url=thumb)
    return embed


def _format_added_line(meta: dict) -> str:
    """Return a concise plain-text description of the added video."""
    title = meta.get("title", "")
    channel = meta.get("channel_title", "")
    duration = _format_duration(int(meta.get("duration_seconds", 0)))
    return f"Added: {title} — {channel} ({duration})"


def _build_announcement_content(content_prefix: str | None, line: str) -> str:
    """Compose the public success message content."""

    parts: list[str] = []
    if content_prefix:
        parts.append(content_prefix)
    parts.append(line)
    playlist_url = _resolve_playlist_url()
    if playlist_url:
        parts.append(f"Listen to the playlist: {playlist_url}")
    return "\n".join(parts)


async def _announce_added(
    *,
    meta: dict,
    content_prefix: str | None,
    channel,
    fallback_sender,
) -> None:
    """Send a public announcement with optional prefix and embed.

    Tries the provided ``channel`` first; if unavailable, uses the
    ``fallback_sender`` callable (e.g., ``interaction.followup.send``).
    """
    embed = _build_video_embed(meta)
    line = _format_added_line(meta)
    content = _build_announcement_content(content_prefix, line)

    try:
        if channel is not None:
            if embed is not None:
                await channel.send(content=content, embed=embed)
            else:
                await channel.send(content)
            return
    except Exception:
        logging.exception("Failed to post in channel; will try fallback")

    # Fallback path if channel was None or send failed
    try:
        if embed is not None:
            await fallback_sender(content=content, embed=embed)
        else:
            await fallback_sender(content)
    except Exception as exc:
        # Swallow Unknown interaction errors (token expired) to avoid noisy exceptions
        if _is_unknown_interaction_error(exc):
            logging.debug("Fallback sender hit Unknown interaction; suppressing")
            return
        raise


async def _resolve_channel_for_interaction(interaction):
    """Return a channel object for an interaction, preferring the current one.

    Falls back to the configured ``CHANNEL_ID`` if necessary.
    """
    channel = getattr(interaction, "channel", None)
    if channel is not None:
        return channel
    if CHANNEL_ID is not None:
        try:
            return bot.get_channel(CHANNEL_ID) or await bot.fetch_channel(CHANNEL_ID)
        except Exception:
            logging.debug("Failed to fetch fallback channel", exc_info=True)
    return None


async def _get_cooldown_remaining(user_id: int, *, now: float | None = None) -> float:
    """Return the remaining cooldown in seconds for ``user_id``."""

    if ADDRADIO_COOLDOWN_SECONDS <= 0:
        return 0.0

    current = time.time() if now is None else now
    async with _user_cooldown_lock:
        last = _user_cooldowns.get(user_id)
        if last is None:
            return 0.0
        remaining = ADDRADIO_COOLDOWN_SECONDS - (current - last)
    return remaining if remaining > 0 else 0.0


async def _mark_cooldown(user_id: int, *, now: float | None = None) -> None:
    """Record the current timestamp for ``user_id``'s cooldown."""

    if ADDRADIO_COOLDOWN_SECONDS <= 0:
        return

    current = time.time() if now is None else now
    async with _user_cooldown_lock:
        _user_cooldowns[user_id] = current


async def _start_health_server() -> None:
    """Start a lightweight health HTTP server on HEALTH_PORT.

    Exposes `/healthz` returning JSON with status, readiness, and uptime.
    Uses aiohttp if available via discord.py dependency.
    """

    if web is None:
        logging.warning("Health server unavailable: aiohttp not importable")
        return

    app = web.Application()

    async def health(_request):
        return web.json_response({
            "status": "ok",
            "ready": bot.is_ready(),
            "uptime_s": int(time.time() - START_TIME),
        })

    app.add_routes([web.get("/healthz", health), web.get("/", health)])

    host = os.getenv("HEALTH_HOST", "0.0.0.0")
    port = int(os.getenv("HEALTH_PORT", "8081"))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=host, port=port)
    await site.start()
    logging.info("Health server started on http://%s:%s/healthz", host, port)

@bot.event
async def on_ready():
    global _health_started
    logging.info(f"Logged in as {bot.user}")

    # Start health endpoint once
    if not _health_started:
        try:
            bot.loop.create_task(_start_health_server())
            _health_started = True
        except Exception:
            logging.exception("Failed to start health server")

    health_port = os.getenv("HEALTH_PORT", "8081")
    logging.info("READY playlist=%s channel=%s health=http://localhost:%s/healthz",
                 PLAYLIST, CHANNEL_ID, health_port)

    # Sync slash commands
    if tree is not None:
        try:
            if GUILD_ID:
                guild_obj = discord.Object(id=GUILD_ID)
                try:
                    tree.copy_global_to(guild=guild_obj)
                except Exception:
                    logging.debug("copy_global_to failed (maybe no globals yet)", exc_info=True)
                await tree.sync(guild=guild_obj)
                logging.info("Slash commands synced to guild %s", GUILD_ID)
            else:
                await tree.sync()
                logging.info("Slash commands synced globally")
        except Exception:
            logging.exception("Failed to sync slash commands")

    # Ready announcement intentionally removed to avoid extra noise in the channel

# Slash command: /addradio (available when app_commands is present)
if tree is not None:
    @tree.command(name="addradio", description="Add a YouTube video to the playlist")
    @app_commands.describe(url="YouTube URL")
    async def addradio(interaction, url: str):
        try:
            # Restrict to configured channel if set
            if CHANNEL_ID is not None and getattr(interaction, "channel_id", None) != CHANNEL_ID:
                await interaction.response.send_message(
                    f"Please use this command in <#{CHANNEL_ID}>.", ephemeral=True
                )
                return

            user = getattr(interaction, "user", None)
            user_id = getattr(user, "id", None)
            if user_id is not None:
                remaining = await _get_cooldown_remaining(user_id)
                if remaining > 0:
                    wait_seconds = max(1, math.ceil(remaining))
                    await interaction.response.send_message(
                        "Please wait "
                        f"{wait_seconds} more seconds before adding more songs. "
                        "Tip: you can add multiple tracks at once by including a "
                        "comma-separated list of YouTube links.",
                        ephemeral=True,
                    )
                    return

            # Defer early to allow slower YouTube API calls, but do it silently
            # (no visible "thinking…" message) to avoid double confirmations.
            await interaction.response.defer(ephemeral=True)

            vids = canonical_video_ids_from_text(url)
            if not vids:
                await _safe_followup_send(
                    interaction,
                    "No valid YouTube video URL found.", ephemeral=True
                )
                return

            if user_id is not None:
                await _mark_cooldown(user_id)

            user_mention = (
                getattr(user, "mention", None)
                or getattr(user, "name", None)
                or "someone"
            )
            content_prefix = f"Song added by {user_mention}"
            channel = await _resolve_channel_for_interaction(interaction)

            added: list[tuple[str, str]] = []
            duplicates: list[str] = []
            too_long: list[tuple[str, str]] = []
            failures: list[tuple[str, str]] = []

            for vid in vids:
                try:
                    if await _call_with_retry(
                        video_exists,
                        vid,
                        PLAYLIST,
                        description=f"check playlist for {vid}",
                    ):
                        duplicates.append(vid)
                        continue

                    meta = await _call_with_retry(
                        get_video_metadata,
                        vid,
                        description=f"fetch metadata for {vid}",
                    )
                    title = meta.get("title") or vid

                    if int(meta.get("duration_seconds", 0)) > MAX_VIDEO_DURATION_SECONDS:
                        too_long.append((vid, title))
                        continue

                    await _call_with_retry(
                        add_to_playlist,
                        vid,
                        PLAYLIST,
                        description=f"add video {vid}",
                    )

                    await _announce_added(
                        meta=meta,
                        content_prefix=content_prefix,
                        channel=channel,
                        fallback_sender=interaction.followup.send,
                    )

                    added.append((vid, title))
                except CredentialsExpiredError as e:
                    await _safe_followup_send(interaction, str(e), ephemeral=True)
                    return
                except Exception as exc:
                    logging.exception("Couldn't add video via slash command: %s", vid)
                    failures.append((vid, str(exc)))

            summary_parts: list[str] = []
            if added:
                added_lines = "\n".join(
                    f"• {title} (`{vid}`)" for vid, title in added
                )
                summary_parts.append("Added to the playlist:\n" + added_lines)
            if duplicates:
                duplicate_lines = "\n".join(f"• `{vid}`" for vid in duplicates)
                summary_parts.append("Already in the playlist:\n" + duplicate_lines)
            if too_long:
                too_long_lines = "\n".join(
                    f"• {title} (`{vid}`)" for vid, title in too_long
                )
                summary_parts.append("Too long (>10 minutes):\n" + too_long_lines)
            if failures:
                failure_lines = "\n".join(
                    f"• `{vid}` — {error}" for vid, error in failures
                )
                summary_parts.append("Failed to add:\n" + failure_lines)
            if not summary_parts:
                summary_parts.append("No videos were processed.")

            await _safe_followup_send(
                interaction,
                "\n\n".join(summary_parts),
                ephemeral=True,
            )
        except CredentialsExpiredError as e:
            await _safe_followup_send(interaction, str(e), ephemeral=True)
        except Exception as e:
            logging.exception("Couldn't add video via slash command: %s", url)
            # Try to inform the user; suppress Unknown interaction error
            try:
                await _safe_followup_send(interaction, f"Couldn't add video: {e}", ephemeral=True)
            except Exception:
                logging.debug("Failed to notify user about error", exc_info=True)

if __name__ == "__main__":
    bot.run(TOKEN)
