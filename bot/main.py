import os, re, logging, asyncio
import discord
from dotenv import load_dotenv
from .youtube import add_to_playlist, video_exists

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

@bot.event
async def on_ready():
    logging.info(f"Logged in as {bot.user}")

@bot.event
async def on_message(msg: discord.Message):
    if msg.author.bot or msg.channel.id != CHANNEL_ID:
        return
    if KEYWORD not in msg.content.lower():
        return

    vids = YTRX.findall(msg.content)
    if not vids:
        return

    for vid in vids:
        try:
            if video_exists(vid, PLAYLIST):
                await msg.add_reaction("🔁")  # already there
                continue
            add_to_playlist(vid, PLAYLIST)
            await msg.add_reaction("✅")
        except Exception as e:
            logging.exception("Couldn't add video %s to playlist %s", vid, PLAYLIST)
            await msg.add_reaction("❌")
            await msg.reply(f"Couldn't add `{vid}`: {e}")

bot.run(TOKEN)
