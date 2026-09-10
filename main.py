import discord
from discord.ext import commands
import os
import json
import logging
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

from utils.calendar import list_upcoming_events, CALENDAR_ID

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    logging.info(f"Logged in as {bot.user} (ID: {bot.user.id})")
    
    # Update nickname in all servers to 'Cherry'
    for guild in bot.guilds:
        try:
            if guild.me.nick != "Cherry":
                await guild.me.edit(nick="Cherry")
        except discord.Forbidden:
            logging.warning(f"Lacking permissions to change nickname in {guild.name}")
    
    # Load cogs
    try:
        await bot.load_extension('cogs.assistant')
        logging.info("Loaded assistant cog successfully.")
    except Exception as e:
        logging.error(f"Failed to load extension cogs.assistant: {e}")
        return

    # Calendar startup check
    try:
        logging.info(f"Checking Google Calendar connection (Target ID: {CALENDAR_ID})...")
        list_upcoming_events(days=1)
        logging.info("Calendar connection successful.")
    except Exception as e:
        logging.error(f"Calendar check failed! Check your GOOGLE_CALENDAR_ID and credentials. Error: {e}")

    # Catch-up phase
    logging.info("Starting catch-up phase...")
    assistant_cog = bot.get_cog('Assistant')
    if not assistant_cog:
        logging.error("Assistant cog not found for catch-up.")
        return

    last_read_data = {}
    if os.path.exists('last_read.json'):
        with open('last_read.json', 'r') as f:
            try:
                last_read_data = json.load(f)
            except json.JSONDecodeError:
                pass

    for guild in bot.guilds:
        for channel in guild.text_channels:
            if str(channel.id) in assistant_cog.exclude_channels or channel.name in assistant_cog.exclude_channels:
                continue

            last_id = last_read_data.get(str(channel.id))
            try:
                if last_id:
                    # Fetch messages after last_id
                    last_message = await channel.fetch_message(int(last_id))
                    async for msg in channel.history(limit=100, after=last_message, oldest_first=True):
                        if msg.author != bot.user:
                            await assistant_cog.process_task(msg)
                else:
                    # No last_id, fetch last 24 hours
                    after_time = datetime.now(timezone.utc) - timedelta(hours=24)
                    async for msg in channel.history(limit=100, after=after_time, oldest_first=True):
                        if msg.author != bot.user:
                            await assistant_cog.process_task(msg)
            except discord.Forbidden:
                logging.warning(f"Forbidden to read history in {channel.name}")
            except discord.HTTPException as e:
                logging.error(f"HTTPException reading history in {channel.name}: {e}")
            except Exception as e:
                logging.error(f"Error during catch-up in {channel.name}: {e}")

    logging.info("Catch-up phase complete. Listening for new messages.")

if __name__ == "__main__":
    if not TOKEN:
        logging.error("DISCORD_TOKEN environment variable not found. Exiting.")
        exit(1)
    
    bot.run(TOKEN)
