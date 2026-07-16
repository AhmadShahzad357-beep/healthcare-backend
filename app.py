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

# ========================================
# ✅ PATH SETUP (Naye structure ke mutabiq)
# ========================================
BASE_DIR = Path(__file__).resolve().parent
env_path = BASE_DIR / ".env"
load_dotenv(dotenv_path=env_path)

# Project root ko sys.path mein add karein
sys.path.insert(0, str(BASE_DIR))

# ========================================
# ✅ NAYE IMPORTS (src/ ki jagah rag/ aur database/)
# ========================================
from config import GROQ_MODEL, TEMPERATURE, MAX_TOKENS
from rag.agent import route_query
from database.patient_db import PatientDB
from rag.safety_guard import SafetyGuard
from rag.cache import get_cached_response, set_cached_response

# ========================================
# FASTAPI APP
# ========================================
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ========================================
# GROQ CLIENT
# ========================================
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
print(f"🔑 API Key Loaded: {'Yes' if GROQ_API_KEY else 'No'}")

try:
    from groq import Groq
    groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
except Exception as e:
    print(f"❌ Groq init error: {e}")
    groq_client = None

# ========================================
# DATABASE & SAFETY
# ========================================
safety = SafetyGuard()
db = PatientDB()

# ========================================
# SYSTEM PROMPT
# ========================================
BASE_SYSTEM_PROMPT = """
You are a strict medical assistant for a hospital.
🔒 RULES:
1. You will be given "MEDICAL CONTEXT".
2. ONLY answer based on this context. If not present, say "I don't know".
3. NEVER diagnose. Always recommend: "Please consult a doctor."
4. Match the user's language (Roman/English).
"""

def get_dynamic_system_prompt(query: str, patient_id: int) -> str:
    routed = route_query(query, patient_id=patient_id)
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

def process_query_logic(query: str, patient_id: int) -> str:
    session_id = db.create_session(patient_id, title=query[:30] + "...")
    system_prompt = get_dynamic_system_prompt(query, patient_id)
    history = db.get_session_history(patient_id, session_id, limit=10)
    
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

# ========================================
# WHATSAPP WEBHOOK (Full RAG)
# ========================================
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
            reply = process_query_logic(incoming_msg, patient_id)
            set_cached_response(incoming_msg, patient_id, reply)
        
        resp = MessagingResponse()
        resp.message(reply)
        return PlainTextResponse(content=str(resp), media_type="application/xml")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return PlainTextResponse(content="Error", status_code=500)

# ========================================
# CHAT ENDPOINT (Web)
# ========================================
class ChatRequest(BaseModel):
    query: str
    session_id: str | None = None

@app.post("/chat")
async def chat_endpoint(req: ChatRequest):
    if not req.query:
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    patient_id = 1
    reply = process_query_logic(req.query, patient_id)
    return {"response": reply}

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

# ========================================
# FRONTEND (Optional)
# ========================================
frontend_path = BASE_DIR / "frontend"
if frontend_path.exists():
    app.mount("/", StaticFiles(directory=str(frontend_path), html=True), name="frontend")

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)