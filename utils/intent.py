import os
import requests
import json
import logging
from dotenv import load_dotenv

load_dotenv()
OLLAMA_MODEL = os.getenv('OLLAMA_MODEL', 'qwen')

def classify_intent(message_content):
    """
    Classifies an incoming message into one of three intents:
    - task: something to schedule (event, deadline, assignment)
    - task_query: a question about existing plans/schedule
    - general_chat: casual conversation, brainstorming, anything else
    """
    url = "http://localhost:11434/api/chat"
    prompt = f"""
    Classify the intent of the following message into exactly one of these three categories:
    1. "task": The user wants to schedule an event, deadline, or assignment.
    2. "task_query": The user is asking a question about their existing plans or schedule.
    3. "general_chat": Casual conversation, brainstorming, providing information, or anything else.

    Return ONLY a valid JSON object with the exact key "intent" and the classified string value. Do not return any other text.
    
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
        data = json.loads(raw_response)
        intent = data.get("intent", "general_chat").lower()
        if intent not in ["task", "task_query", "general_chat"]:
            intent = "general_chat"
        return intent
    except Exception as e:
        logging.error(f"Error classifying intent: {e}")
        return "general_chat" # fallback
