import discord
import os
import json
import google.generativeai as genai
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
CHANNEL_ID = int(os.getenv('CHANNEL_ID'))
CALENDAR_ID = os.getenv('CALENDAR_ID')

# Gemini setup
genai.configure(api_key=os.getenv('GEMINI_API_KEY'))
model = genai.GenerativeModel('gemini-1.5-flash')

# Calendar setup
SCOPES = ['https://www.googleapis.com/auth/calendar.events']
creds = Credentials.from_service_account_file('credentials.json', scopes=SCOPES)
calendar_service = build('calendar', 'v3', credentials=creds)

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

def get_last_read():
    try:
        with open('last_read.txt', 'r') as f:
            content = f.read().strip()
            return int(content) if content else None
    except FileNotFoundError:
        return None

def update_last_read(message_id):
    with open('last_read.txt', 'w') as f:
        f.write(str(message_id))

async def process_task(message):
    print(f"\nNew message received: {message.content}")
    
    if message.content.lower().strip() in ["hi", "hello", "hey", "hey cherry"]:
        await message.reply("Hey! Cherry is online and ready for tasks 🍒")
        update_last_read(message.id)
        return

    prompt = f"""
    Analyze this message and extract the task details.
    Current Date/Time reference: Sunday, September 6, 2026, IST.
    
    Required JSON format:
    "title": A short name for the task.
    "category": Sort into either "Club", "Hackathon", "Curriculum", "Assignment", or "General".
    "deadline": Calculate the exact ISO 8601 timestamp (YYYY-MM-DDTHH:MM:SS) if a time/date is mentioned. If not, return null.
    "notes": Any extra context or instructions mentioned.

    Message: "{message.content}"
    """
    
    try:
        response = model.generate_content(
            prompt,
            generation_config={"response_mime_type": "application/json"}
        )
        task_data = json.loads(response.text)
        print(f"Extracted Data:\n{json.dumps(task_data, indent=2)}")
        
        reply_msg = f"Got it! Logged **{task_data.get('title', 'task')}** under **{task_data.get('category')}**."
        
        # Calendar Logic
        if task_data.get('deadline'):
            event = {
                'summary': f"[{task_data.get('category')}] {task_data.get('title')}",
                'description': task_data.get('notes', ''),
                'start': {
                    'dateTime': task_data.get('deadline'),
                    'timeZone': 'Asia/Kolkata',
                },
                'end': {
                    'dateTime': task_data.get('deadline'),
                    'timeZone': 'Asia/Kolkata',
                },
            }
            created_event = calendar_service.events().insert(calendarId=CALENDAR_ID, body=event).execute()
            reply_msg += f"\n📅 [Scheduled in Calendar]({created_event.get('htmlLink')})"
            
        await message.add_reaction("✅")
        await message.reply(reply_msg)
        update_last_read(message.id)
        
    except Exception as e:
        print(f"Error parsing task: {e}")
        await message.add_reaction("❌")

@client.event
async def on_ready():
    print(f'Logged in as {client.user}')
    channel = client.get_channel(CHANNEL_ID)
    last_id = get_last_read()

    if last_id and channel:
        print("Checking for missed messages...")
        try:
            last_message = await channel.fetch_message(last_id)
            async for msg in channel.history(after=last_message, oldest_first=True):
                if msg.author == client.user:
                    continue
                await process_task(msg)
        except Exception as e:
            print(f"Could not fetch history: {e}")
            
    print("Up to date. Listening for new messages...")

@client.event
async def on_message(message):
    if message.author == client.user or message.channel.id != CHANNEL_ID:
        return
    await process_task(message)

client.run(TOKEN)