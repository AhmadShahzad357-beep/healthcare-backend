import os
import sys
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from fastapi.responses import PlainTextResponse
import uvicorn
from dotenv import load_dotenv
from twilio.twiml.messaging_response import MessagingResponse

env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=env_path)

sys.path.append(str(Path(__file__).resolve().parent))
from config import GROQ_MODEL, TEMPERATURE, MAX_TOKENS
import src.agent as agent
from src.patient_db import PatientDB
from src.safety_guard import SafetyGuard
from src.cache import get_cached_response, set_cached_response

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
print(f"?? API Key Loaded: {'Yes' if GROQ_API_KEY else 'No'}")

try:
    from groq import Groq
    groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
except Exception as e:
    print(f"? Groq init error: {e}")
    groq_client = None

safety = SafetyGuard()
db = PatientDB()

BASE_SYSTEM_PROMPT = """
You are a medical assistant with access to WHO medical guidelines.
?? RULES:
1. You will be given "MEDICAL CONTEXT".
2. Answer directly based on the context. If context is empty, say "I don't know."
3. You are allowed to provide factual medical information. Do not add extra disclaimers unless asked.
4. LANGUAGE: Reply in English or Roman Urdu only.
"""

def get_dynamic_system_prompt(query: str, patient_id: int) -> str:
    routed = agent.route_query(query, patient_id=patient_id)
    intent = routed['intent']
    context_str = ""
    if intent == "history_rag":
        context_str = routed['data'].get('context', 'No past chats found.')
    elif intent == "patient_db":
        data = routed['data']
        if data and data.get('profile'):
            profile = data['profile']
            context_str = f"Patient: {profile['name']}, Age: {profile['age']}, Blood Group: {profile['blood_group']}, Allergies: {profile['allergies']}\n"
            if data.get('reports'):
                context_str += "Reports: " + ", ".join([f"{r['test_name']}: {r['result']} {r['unit']}" for r in data['reports'][:3]])
    elif intent == "medicine_api":
        data = routed['data']
        if data and data.get('interaction_found'):
            context_str = f"Interaction: {data['severity']}. {data['message']}"
        else:
            context_str = "No major interaction."
    elif intent == "retrieval":
        context_str = routed['data'].get('context', 'No relevant medical data.')
    return f"{BASE_SYSTEM_PROMPT}\n\n--- CONTEXT ---\n{context_str}\n--- END ---"

def process_query_logic(query: str, patient_id: int, session_id: str = None) -> str:
    if session_id is None: session_id = db.create_session(patient_id, title=query[:30] + "...")
    system_prompt = get_dynamic_system_prompt(query, patient_id)
    history = db.get_session_history(patient_id, session_id, limit=2)
    
    messages = [{"role": "system", "content": system_prompt}]
    for turn in history:
        messages.append({"role": "user", "content": turn['user']})
        messages.append({"role": "assistant", "content": turn['bot']})
    messages.append({"role": "user", "content": query})
    
    if "No relevant" in system_prompt or "No data" in system_prompt or "No past chats" in system_prompt:
        reply = "I don't know. Please consult a doctor." if query[0].isalpha() else "Mujhe nahi pata. Kripya doctor se rabta karein."
        db.save_conversation_with_session(patient_id, session_id, query, reply)
        return reply
    
    try:
        response = groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=messages,
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS
        )
        reply = response.choices[0].message.content
        db.save_conversation_with_session(patient_id, session_id, query, reply)
        return reply
    except Exception as e:
        return f"Error: {str(e)}"

@app.post("/whatsapp")
async def whatsapp_webhook(request: Request):
    try:
        form = await request.form()
        incoming_msg = form.get('Body', '').strip()
        sender = form.get('From', '').replace("whatsapp:", "")
        print(f"?? WhatsApp: {sender} -> {incoming_msg}")
        patient_id = req.patient_id
        cached = get_cached_response(incoming_msg, patient_id)
        if cached:
            reply = cached
        else:
            reply = process_query_logic(incoming_msg, patient_id)
            set_cached_response(incoming_msg, patient_id, reply)
        resp = MessagingResponse()
        resp.message(reply)
        return PlainTextResponse(content=str(resp), media_type="application/xml")
    except Exception as e:
        print(f"? Error: {e}")
        return PlainTextResponse(content="Error", status_code=500)

class ChatRequest(BaseModel):
    query: str
    session_id: str | None = None
    patient_id: int = 1

