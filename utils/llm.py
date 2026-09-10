import os
import requests
import json
import logging
from dotenv import load_dotenv

load_dotenv()
OLLAMA_MODEL = os.getenv('OLLAMA_MODEL', 'qwen')

def extract_task_details(message_content, current_time):
    url = "http://localhost:11434/api/chat"
    prompt = f"""
    Analyze this message and extract the task details.
    Current Date/Time reference: {current_time}.
    
    Return ONLY a valid JSON object with these exact keys:
    "title": A short name for the task.
    "category": Sort into either "Club", "Hackathon", "Curriculum", "Assignment", or "General".
    "start_time": ISO 8601 timestamp (YYYY-MM-DDTHH:MM:SS) for start. If only a deadline is given, use that as end_time and set start_time 1 hour prior. If no time is mentioned, return null.
    "end_time": ISO 8601 timestamp (YYYY-MM-DDTHH:MM:SS) for deadline/end. If none, return null.
    "notes": Any extra context mentioned.

    Message: "{message_content}"
    """
    
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "format": "json"
    }
    
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        raw_response = response.json()['message']['content']
        return json.loads(raw_response)
    except Exception as e:
        logging.error(f"Error extracting task: {e}")
        raise e

def generate_chat_response(message_content, memory_content):
    url = "http://localhost:11434/api/chat"
    system_prompt = f"You are a helpful personal assistant named Cherry. Here is what you know about the user so far:\n{memory_content}"
    
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message_content}
        ],
        "stream": False
    }
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        return response.json()['message']['content']
    except Exception as e:
        logging.error(f"Error in chat response: {e}")
        return "I'm having trouble thinking right now."

def generate_task_query_response(message_content, upcoming_events_text, memory_content):
    url = "http://localhost:11434/api/chat"
    system_prompt = f"""You are a helpful personal assistant named Cherry. 
Here is what you know about the user so far:
{memory_content}

Here are the upcoming calendar events:
{upcoming_events_text}

Answer the user's question about their schedule based on this information. You MUST include the actual event links (provided in the events list) in your response so the user can click them!"""
    
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message_content}
        ],
        "stream": False
    }
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        return response.json()['message']['content']
    except Exception as e:
        logging.error(f"Error in task query response: {e}")
        return "I couldn't check your schedule."

def extract_memory_update(message_content):
    url = "http://localhost:11434/api/chat"
    prompt = f"""
    Analyze the following user message and determine if there is any new, important long-term information worth remembering (e.g., ongoing projects, preferences, deadlines mentioned in passing).
    If there is, return a concise summary of the fact to remember.
    If there is nothing worth remembering, return exactly the string "NONE".
    
    Message: "{message_content}"
    """
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False
    }
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        content = response.json()['message']['content'].strip()
        if content == "NONE" or "NONE" in content.upper():
            return None
        return content
    except Exception as e:
        logging.error(f"Error extracting memory: {e}")
        return None

def compress_memory(current_memory):
    url = "http://localhost:11434/api/chat"
    prompt = f"""
    Please compress and summarize the following memory text. Keep all important facts, preferences, and long-term projects, but drop stale or redundant information. Return only the compressed text.
    
    Memory to compress:
    {current_memory}
    """
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False
    }
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        return response.json()['message']['content'].strip()
    except Exception as e:
        logging.error(f"Error compressing memory: {e}")
        return current_memory
