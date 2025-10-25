import os, logging, asyncio, time

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

async def _safe_followup_send(interaction, content: str | None = None, *, ephemeral: bool = True, embed=None):
    """Attempt to send an interaction followup; fall back to channel on Unknown interaction.

    If the interaction token has expired (10062), try posting in the resolved
    channel instead so users still get feedback.
    """
    try:
        if embed is not None:
            await interaction.followup.send(content=content, ephemeral=ephemeral, embed=embed)
        else:
            await interaction.followup.send(content, ephemeral=ephemeral)
    except Exception as exc:
        if _is_unknown_interaction_error(exc):
            logging.debug("Interaction followup token expired; falling back to channel")
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
            # Give up quietly if both paths fail
            return
        # Re-raise unexpected errors
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
KEYWORD = "730radio"
ENABLE_MESSAGE_SCANNING = _bool_from_env("ENABLE_MESSAGE_SCANNING", default=True)

logging.basicConfig(level=logging.INFO)
intents = discord.Intents.default()
if ENABLE_MESSAGE_SCANNING:
    intents.message_content = True
bot = discord.Client(intents=intents)
 
# Slash commands (discord.app_commands) if available
app_commands = getattr(discord, "app_commands", None)
tree = app_commands.CommandTree(bot) if app_commands else None

START_TIME = time.time()
_health_started = False
MAX_VIDEO_DURATION_SECONDS = 10 * 60


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
    content = (f"{content_prefix} — {line}") if content_prefix else line

    try:
        if channel is not None:
            if embed is not None:
                await channel.send(content=content_prefix or None, embed=embed)
            else:
                await channel.send(content)
            return
    except Exception:
        logging.exception("Failed to post in channel; will try fallback")

    # Fallback path if channel was None or send failed
    try:
        if embed is not None:
            await fallback_sender(content=content_prefix or None, embed=embed)
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

# Optional legacy keyword scanning (can be disabled via ENABLE_MESSAGE_SCANNING=0)
if ENABLE_MESSAGE_SCANNING:
    @bot.event
    async def on_message(msg: discord.Message):
        if msg.author.bot or msg.channel.id != CHANNEL_ID:
            return
        if KEYWORD not in msg.content.lower():
            return

        vids = canonical_video_ids_from_text(msg.content)
        if not vids:
            return

        for vid in vids:
            try:
                if video_exists(vid, PLAYLIST):
                    await msg.add_reaction("🔁")
                    continue
                meta = get_video_metadata(vid)
                if int(meta.get("duration_seconds", 0)) > MAX_VIDEO_DURATION_SECONDS:
                    await msg.add_reaction("⏱️")
                    await msg.reply(
                        "Videos longer than 10 minutes are not allowed on the playlist."
                    )
                    continue
                add_to_playlist(vid, PLAYLIST)
                await msg.add_reaction("✅")
                await _announce_added(
                    meta=meta,
                    content_prefix=None,
                    channel=msg.channel,
                    fallback_sender=msg.channel.send,
                )
            except CredentialsExpiredError as e:
                await msg.add_reaction("❌")
                await msg.reply(str(e))
                return
            except Exception as e:
                logging.exception("Couldn't add video %s to playlist %s", vid, PLAYLIST)
                await msg.add_reaction("❌")
                await msg.reply(f"Couldn't add `{vid}`: {e}")


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

            # Defer early to allow slower YouTube API calls, but do it silently
            # (no visible "thinking…" message) to avoid double confirmations.
            await interaction.response.defer()

            vids = canonical_video_ids_from_text(url)
            if not vids:
                await _safe_followup_send(
                    interaction,
                    "No valid YouTube video URL found.", ephemeral=True
                )
                return

            # Take the first parsed video ID
            vid = vids[0]

            if video_exists(vid, PLAYLIST):
                await _safe_followup_send(
                    interaction,
                    f"Video `{vid}` is already in the playlist. 🔁", ephemeral=True
                )
                return

            meta = get_video_metadata(vid)
            if int(meta.get("duration_seconds", 0)) > MAX_VIDEO_DURATION_SECONDS:
                await _safe_followup_send(
                    interaction,
                    "Videos longer than 10 minutes are not allowed on the playlist.",
                    ephemeral=True,
                )
                return

            add_to_playlist(vid, PLAYLIST)

            # Public announcement in the channel for everyone, with requester mention
            user = getattr(interaction, "user", None)
            user_mention = (
                getattr(user, "mention", None)
                or getattr(user, "name", None)
                or "someone"
            )
            content_prefix = f"Added by {user_mention}"
            channel = await _resolve_channel_for_interaction(interaction)
            await _announce_added(
                meta=meta,
                content_prefix=content_prefix,
                channel=channel,
                fallback_sender=interaction.followup.send,
            )

            # Always clear the deferred "thinking" state with an ephemeral ack
            await _safe_followup_send(
                interaction,
                "Video added to the playlist. ✅",
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
