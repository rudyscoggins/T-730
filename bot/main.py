import os, re, logging, asyncio, time
import discord
from dotenv import load_dotenv
from .youtube import add_to_playlist, video_exists
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

TOKEN      = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
PLAYLIST   = os.getenv("PLAYLIST_ID")
KEYWORD    = "730radio"

logging.basicConfig(level=logging.INFO)
intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)

START_TIME = time.time()
_health_started = False


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

    # Optional: send a ready message to the configured channel
    try:
        ch = bot.get_channel(CHANNEL_ID) or await bot.fetch_channel(CHANNEL_ID)
        if ch:
            await ch.send(f"730RadioBot is online. Listening for '" + KEYWORD + "'.")
    except Exception:
        # Non-fatal if we can't announce in channel
        logging.debug("Ready announcement skipped or failed", exc_info=True)

@bot.event
async def on_message(msg: discord.Message):
    if msg.author.bot or msg.channel.id != CHANNEL_ID:
        return
    if KEYWORD not in msg.content.lower():
        return

    # Extract canonical video IDs from the message content, supporting
    # multiple URL variants (watch, youtu.be, shorts, embed, etc.).
    vids = canonical_video_ids_from_text(msg.content)
    if not vids:
        return

    for vid in vids:
        try:
            if video_exists(vid, PLAYLIST):
                await msg.add_reaction("🔁")  # already there
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

if __name__ == "__main__":
    bot.run(TOKEN)
