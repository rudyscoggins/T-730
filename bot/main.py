import os, re, logging, asyncio, time

try:  # pragma: no cover - exercised indirectly via tests when discord missing
    import discord  # type: ignore
except Exception as exc:  # pragma: no cover - the fallback itself is tested
    logging.getLogger(__name__).warning(
        "discord import failed (%s); using lightweight stub", exc,
    )
    from . import discord_stub as discord  # type: ignore
from dotenv import load_dotenv
from .youtube import add_to_playlist, video_exists, get_video_duration_seconds
from .youtube import CredentialsExpiredError
from .youtube.urls import canonical_video_ids_from_text

try:
    # discord.py depends on aiohttp; use it for an in-process health endpoint
    from aiohttp import web  # type: ignore
except Exception:  # pragma: no cover - only if aiohttp missing at runtime
    web = None  # type: ignore
from .youtube.urls import canonical_video_ids_from_text

# Legacy regex retained for compatibility if needed, but URL parsing below
# now handles multiple variants and deduplication.
YTRX = re.compile(r"(?:youtu\.be/|youtube\.com/watch\?v=)([A-Za-z0-9_-]{11})",
                  re.IGNORECASE)

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


TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = _int_from_env("CHANNEL_ID")
GUILD_ID = _int_from_env("GUILD_ID")
PLAYLIST = os.getenv("PLAYLIST_ID")
KEYWORD = "730radio"
ENABLE_MESSAGE_SCANNING = os.getenv("ENABLE_MESSAGE_SCANNING", "1") == "1"

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

    # Optional: send a ready message to the configured channel
    if CHANNEL_ID is not None:
        try:
            ch = bot.get_channel(CHANNEL_ID) or await bot.fetch_channel(CHANNEL_ID)
            if ch:
                await ch.send(f"T-730 operational.  Listening for {KEYWORD}")
        except Exception:
            # Non-fatal if we can't announce in channel
            logging.debug("Ready announcement skipped or failed", exc_info=True)

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
                duration = get_video_duration_seconds(vid)
                if duration > MAX_VIDEO_DURATION_SECONDS:
                    await msg.add_reaction("⏱️")
                    await msg.reply(
                        "Videos longer than 10 minutes are not allowed on the playlist."
                    )
                    continue
                add_to_playlist(vid, PLAYLIST)
                await msg.add_reaction("✅")
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

            await interaction.response.defer(thinking=True, ephemeral=True)

            vids = canonical_video_ids_from_text(url)
            if not vids:
                await interaction.followup.send(
                    "No valid YouTube video URL found.", ephemeral=True
                )
                return

            # Take the first parsed video ID
            vid = vids[0]

            if video_exists(vid, PLAYLIST):
                await interaction.followup.send(
                    f"Video `{vid}` is already in the playlist. 🔁", ephemeral=True
                )
                return

            duration = get_video_duration_seconds(vid)
            if duration > MAX_VIDEO_DURATION_SECONDS:
                await interaction.followup.send(
                    "Videos longer than 10 minutes are not allowed on the playlist.",
                    ephemeral=True,
                )
                return

            add_to_playlist(vid, PLAYLIST)
            await interaction.followup.send(
                f"Added `{vid}` to the playlist. ✅", ephemeral=True
            )
        except CredentialsExpiredError as e:
            await interaction.followup.send(str(e), ephemeral=True)
        except Exception as e:
            logging.exception("Couldn't add video via slash command: %s", url)
            await interaction.followup.send(
                f"Couldn't add video: {e}", ephemeral=True
            )

if __name__ == "__main__":
    bot.run(TOKEN)
