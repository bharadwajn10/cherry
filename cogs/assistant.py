import discord
from discord.ext import commands
import os
import json
import logging
from datetime import datetime, timedelta

from utils.intent import classify_intent
from utils.llm import (
    extract_task_details,
    generate_chat_response,
    generate_task_query_response,
    extract_memory_update,
    compress_memory
)
from utils.calendar import add_event, list_upcoming_events

MEMORY_FILE = 'memory.txt'
LAST_READ_FILE = 'last_read.json'
MEMORY_CAP_BYTES = 8192  # 8 KB

def read_memory():
    if not os.path.exists(MEMORY_FILE):
        return ""
    with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
        return f.read()

def write_memory(content):
    with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
        f.write(content)

def append_memory(new_fact):
    memory = read_memory()
    memory += f"\n- {new_fact}"
    write_memory(memory)
    
    # Check size and compress if needed
    if os.path.getsize(MEMORY_FILE) > MEMORY_CAP_BYTES:
        compressed = compress_memory(memory)
        write_memory(compressed)

def update_last_read(channel_id, message_id):
    data = {}
    if os.path.exists(LAST_READ_FILE):
        with open(LAST_READ_FILE, 'r') as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                pass
    data[str(channel_id)] = message_id
    with open(LAST_READ_FILE, 'w') as f:
        json.dump(data, f)

class Assistant(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        exclude_env = os.getenv('EXCLUDE_CHANNELS', '')
        self.exclude_channels = [ch.strip() for ch in exclude_env.split(',')] if exclude_env else []

    @commands.Cog.listener()
    async def on_message(self, message):
        # Ignore messages from the bot itself
        if message.author == self.bot.user:
            return
            
        # Ignore excluded channels
        if str(message.channel.id) in self.exclude_channels or message.channel.name in self.exclude_channels:
            return

        await self.process_task(message)

    async def process_task(self, message):
        logging.info(f"Processing message in {message.channel.name}: {message.content}")
        
        # 1. Classify intent
        intent = classify_intent(message.content)
        logging.info(f"Intent classified as: {intent}")
        
        memory_content = read_memory()
        
        try:
            if intent == "task":
                current_time = datetime.now().strftime("%A, %B %d, %Y, %I:%M %p IST")
                task_data = extract_task_details(message.content, current_time)
                
                end_t = task_data.get('end_time')
                start_t = task_data.get('start_time')
                
                if end_t:
                    if not start_t:
                        dt_end = datetime.fromisoformat(end_t)
                        dt_start = dt_end - timedelta(hours=1)
                        start_t = dt_start.isoformat()
                        
                    summary = f"[{task_data.get('category')}] {task_data.get('title')}"
                    description = task_data.get('notes', '')
                    
                    event_link = add_event(summary, description, start_t, end_t)
                    reply_msg = f"Got it! Logged **{task_data.get('title', 'task')}** under **{task_data.get('category')}**.\n📅 [View Event]({event_link})"
                else:
                    reply_msg = f"I see you want to schedule **{task_data.get('title', 'a task')}**, but I didn't catch a time. When should I schedule it?"
                
                await message.add_reaction("✅")
                await message.reply(reply_msg)
                
            elif intent == "task_query":
                upcoming = list_upcoming_events(days=7)
                response_text = generate_task_query_response(message.content, upcoming, memory_content)
                await message.reply(response_text)
                
            else: # general_chat
                response_text = generate_chat_response(message.content, memory_content)
                await message.reply(response_text)
                
                # Check for memory update
                new_fact = extract_memory_update(message.content)
                if new_fact:
                    append_memory(new_fact)
                    logging.info(f"Appended to memory: {new_fact}")

            # Update last_read.json
            update_last_read(message.channel.id, message.id)
            
        except Exception as e:
            logging.error(f"Error processing message: {e}")
            await message.add_reaction("❌")
            await message.reply(f"Oops, local processing error: `{e}`")

async def setup(bot):
    await bot.add_cog(Assistant(bot))
