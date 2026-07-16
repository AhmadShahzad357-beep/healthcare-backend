import os
import sys
import re
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
print(f"🔑 API Key Loaded: {'Yes' if GROQ_API_KEY else 'No'}")

try:
    from groq import Groq
    groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
except Exception as e:
    print(f"❌ Groq init error: {e}")
    groq_client = None

safety = SafetyGuard()
db = PatientDB()

BASE_SYSTEM_PROMPT = """
You are a strict medical assistant for a hospital.
🔒 RULES:
1. You will be given "MEDICAL CONTEXT".
2. ONLY answer based on this context. If not present, say "I don't know".
3. NEVER diagnose. Always recommend: "Please consult a doctor."
4. LANGUAGE RULE (strict): Always respond in English, UNLESS the user's question is written in Roman Urdu (Urdu written in English letters, e.g. "meri age kitni hai"), in which case respond in Roman Urdu. NEVER respond in French, Spanish, Italian, German, or any other language, regardless of names or context content.
"""

def get_dynamic_system_prompt(query: str, patient_id: int):
    routed = agent.route_query(query, patient_id=patient_id)
    intent = routed['intent']
    found = routed.get('found', False)
    context_str = ""

    if intent == "history_rag":
        context_str = routed['data'].get('context', 'No past chats found.')

    elif intent == "patient_db":
        data = routed['data']
        if data and data.get('profile'):
            profile = data['profile']
            context_str = (
                f"Patient Profile:\n"
                f"- Name: {profile['name']}\n"
                f"- Age: {profile['age']}\n"
                f"- Gender: {profile.get('gender', 'N/A')}\n"
                f"- Contact: {profile.get('contact', 'N/A')}\n"
                f"- Blood Group: {profile['blood_group']}\n"
                f"- Allergies: {profile['allergies']}\n\n"
            )

            history = data.get('history') or []
            if history:
                context_str += "Medical History:\n"
                for h in history[:10]:
                    context_str += f"- {h['condition']} (Diagnosed: {h['diagnosed_date']}, Status: {h['status']})\n"
                context_str += "\n"

            reports = data.get('reports') or []
            if reports:
                context_str += "Recent Lab Reports:\n"
                for r in reports[:5]:
                    context_str += f"- {r['test_name']}: {r['result']} {r['unit']} (Date: {r['date']})\n"
                context_str += "\n"

            apps = data.get('appointments') or []
            if apps:
                context_str += "Appointments:\n"
                for a in apps[:5]:
                    context_str += f"- {a['date']} at {a['time']} with {a['doctor']} ({a.get('department', '')}) - Status: {a['status']}\n"
                context_str += "\n"
        else:
            context_str = "No matching patient record found in the database."

    elif intent == "medicine_api":
        data = routed['data']
        if data and data.get('interaction_found'):
            context_str = f"Interaction: {data['severity']}. {data['message']}"
        elif data:
            context_str = data.get('message', 'No major interaction found.')
        else:
            context_str = "Could not identify two medicine names to compare."

    elif intent == "retrieval":
        context_str = routed['data'].get('context') or "No relevant medical data found in documents."
        context_str = context_str[:2500]  # keep general-RAG context bounded so token usage stays predictable

    system_prompt = f"{BASE_SYSTEM_PROMPT}\n\n--- CONTEXT ---\n{context_str}\n--- END ---"
    return system_prompt, found

def process_query_logic(query: str, patient_id: int, session_id: str | None = None):
    if not session_id:
        session_id = db.create_session(patient_id, title=query[:30] + "...")

    system_prompt, found = get_dynamic_system_prompt(query, patient_id)
    # Only the last 3 turns, and each old reply trimmed - otherwise token usage
    # keeps growing every message in a long session and eventually hits Groq's
    # per-minute token limit (this was causing 413 errors on later messages).
    history = db.get_session_history(patient_id, session_id, limit=3)

    messages = [{"role": "system", "content": system_prompt}]
    for turn in history:
        messages.append({"role": "user", "content": turn['user'][:300]})
        messages.append({"role": "assistant", "content": turn['bot'][:300]})
    messages.append({"role": "user", "content": query})

    if not found:
        is_english = bool(re.search(r'^[a-zA-Z0-9\s\?\.,!]+$', query.strip())) and any(
            w in query.lower() for w in ["what", "is", "are", "the", "my", "how", "when", "who"]
        )
        reply = "I don't know. Please consult a doctor." if is_english else "Mujhe nahi pata. Kripya doctor se rabta karein."
        db.save_conversation_with_session(patient_id, session_id, query, reply)
        return reply, session_id

    try:
        response = groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=messages,
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS
        )
        reply = response.choices[0].message.content
        db.save_conversation_with_session(patient_id, session_id, query, reply)
        return reply, session_id
    except Exception as e:
        return f"Error: {str(e)}", session_id

@app.post("/whatsapp")
async def whatsapp_webhook(request: Request):
    try:
        form = await request.form()
        incoming_msg = form.get('Body', '').strip()
        sender = form.get('From', '').replace("whatsapp:", "")
        print(f"📩 WhatsApp: {sender} -> {incoming_msg}")
        patient_id = 1
        cached = get_cached_response(incoming_msg, patient_id)
        if cached:
            reply = cached
        else:
            reply, _ = process_query_logic(incoming_msg, patient_id)
            set_cached_response(incoming_msg, patient_id, reply)
        resp = MessagingResponse()
        resp.message(reply)
        return PlainTextResponse(content=str(resp), media_type="application/xml")
    except Exception as e:
        print(f"❌ Error: {e}")
        return PlainTextResponse(content="Error", status_code=500)

class ChatRequest(BaseModel):
    query: str
    session_id: str | None = None
    patient_id: int | None = None

@app.post("/chat")
async def chat_endpoint(req: ChatRequest):
    if not req.query:
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    patient_id = req.patient_id or 1
    reply, session_id = process_query_logic(req.query, patient_id, req.session_id)
    return {"response": reply, "session_id": session_id}

@app.get("/sessions")
async def get_sessions(patient_id: int = 1):
    sessions = db.get_sessions(patient_id)
    return {"sessions": sessions}

@app.get("/patients")
async def get_patients():
    patients = db.get_all_patients()
    return {"patients": patients}

@app.get("/session_history/{session_id}")
async def get_session_history(session_id: str, patient_id: int = 1):
    history = db.get_full_session_history(patient_id, session_id)
    return {"history": history}

@app.get("/global_history")
async def get_global_history(patient_id: int = 1, days: int = 30, limit: int = 30):
    history = db.get_global_history(patient_id, days, limit)
    return {"history": history}

frontend_path = Path(__file__).resolve().parent / "frontend"
if frontend_path.exists():
    app.mount("/", StaticFiles(directory=str(frontend_path), html=True), name="frontend")

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
