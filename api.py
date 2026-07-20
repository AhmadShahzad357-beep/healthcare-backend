import os
import sys
import re
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from fastapi.responses import PlainTextResponse
import uvicorn
from dotenv import load_dotenv
from twilio.twiml.messaging_response import MessagingResponse
from twilio.request_validator import RequestValidator
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

env_path = Path(__file__).resolve().parent / ".env"
# encoding="utf-8-sig" safely strips a UTF-8 BOM if present in .env
load_dotenv(dotenv_path=env_path, encoding="utf-8-sig")

sys.path.append(str(Path(__file__).resolve().parent))
from config import (
    GROQ_MODEL, TEMPERATURE, MAX_TOKENS, HOST, PORT, API_BASE_URL,
    API_CONFIG_PATH, API_CHAT_PATH, API_PATIENTS_PATH, API_SESSIONS_PATH,
    API_SESSION_HISTORY_PATH, API_GLOBAL_HISTORY_PATH, API_WHATSAPP_PATH,
)
import src.agent as agent
from src.patient_db import PatientDB
from src.safety_guard import SafetyGuard
from src.cache import get_cached_response, set_cached_response
# NOTE: patient/staff authentication (src/auth.py) is intentionally not
# wired in here. All patient-data routes below trust patient_id as sent
# by the client with no login/token check.

app = FastAPI()

# --- Rate limiting ---------------------------------------------------------
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# --- CORS --------------------------------------------------------------
# No silent "*" fallback: you must explicitly opt into wildcard CORS (only
# ever appropriate for local development), otherwise you must list your
# real frontend domain(s). This matters a lot once real patient data and
# authenticated requests are involved.
_allowed_origins_env = os.getenv("ALLOWED_ORIGINS", "").strip()
if not _allowed_origins_env:
    print("⚠️  ALLOWED_ORIGINS not set in .env — defaulting to http://localhost:3000 (dev only).")
    print("   Set ALLOWED_ORIGINS=https://your-real-domain.com before deploying to production.")
    _allowed_origins = ["http://localhost:3000", "http://127.0.0.1:3000"]
elif _allowed_origins_env == "*":
    print("⚠️  ALLOWED_ORIGINS=* — any website can call this API. Do NOT use this in production.")
    _allowed_origins = ["*"]
else:
    _allowed_origins = [o.strip() for o in _allowed_origins_env.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=_allowed_origins != ["*"],  # browsers reject credentials+"*" anyway
)

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if GROQ_API_KEY:
    print(f"🔑 GROQ_API_KEY loaded (starts with {GROQ_API_KEY[:6]}...)")
else:
    print("❌ GROQ_API_KEY not found in .env — chat responses will fail until this is fixed.")

try:
    from groq import Groq
    groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
except Exception as e:
    print(f"Groq init error: {e}")
    groq_client = None

safety = SafetyGuard()
db = PatientDB()

<<<<<<< HEAD
# Auto-create tables (IF NOT EXISTS) and seed demo patients ONLY if the
# patients table is empty. This is what makes /patients actually return
# data on a fresh deploy (e.g. Railway), where healthcare.db is gitignored
# and never committed, and the old destructive seed script was removed
# from the deploy startCommand on purpose. See src/db_bootstrap.py.
try:
    from src.db_bootstrap import ensure_database_ready
    ensure_database_ready()
except Exception as e:
    print(f"❌ Database bootstrap failed: {e}")

=======
>>>>>>> fd0bbc3d172bfc25f4d6870bdf709ac5dc98e92d
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
_twilio_validator = RequestValidator(TWILIO_AUTH_TOKEN) if TWILIO_AUTH_TOKEN else None

BASE_SYSTEM_PROMPT = """
You are a  medical assistant for a hospital.
RULES:
1. You will be given "MEDICAL CONTEXT".
2. ONLY answer based on this context. If not present, say "I don't know".
3. NEVER diagnose. Always recommend: "Please consult a doctor."
4. LANGUAGE RULE (strict): Always respond in English, UNLESS the user's question is written in Roman Urdu (Urdu written in English letters, e.g. "meri age kitni hai"), in which case respond in Roman Urdu. NEVER respond in French, Spanish, Italian, German, or any other language, regardless of names or context content.
5. NEVER diagnose. Always recommend: "Please consult a doctor."
6. If the CONTEXT above contains information relevant to the question (even partially), you MUST use it to answer — do not say "I don't know" or deflect to "consult a doctor" if the answer is clearly present in the Patient Profile, Medical History, Lab Reports, or Appointments sections.
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

    if not groq_client:
        return "⚠️ The assistant isn't configured correctly. Please contact support.", session_id

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
        # Log the real error server-side only. Never send raw exception
        # details (stack traces, internal paths, library internals) back
        # to the client - that's an information-disclosure risk.
        print(f"❌ Groq call failed: {e}")
        return "Sorry, something went wrong generating a response. Please try again.", session_id

@app.post(API_WHATSAPP_PATH)
@limiter.limit("20/minute")
async def whatsapp_webhook(request: Request):
    try:
        form = await request.form()

        # Verify the request genuinely came from Twilio before doing
        # anything with it. Without this, anyone who finds this URL can
        # POST fake messages, burn your Groq quota, or spoof a sender.
        if _twilio_validator:
            signature = request.headers.get("X-Twilio-Signature", "")
            if not _twilio_validator.validate(str(request.url), dict(form), signature):
                raise HTTPException(status_code=403, detail="Invalid Twilio signature")
        else:
            print("⚠️  TWILIO_AUTH_TOKEN not set — webhook signature is NOT being verified!")

        incoming_msg = form.get('Body', '').strip()[:1000]
        sender = form.get('From', '').replace("whatsapp:", "")
        print(f"WhatsApp: {sender} -> {incoming_msg}")
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
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error: {e}")
        return PlainTextResponse(content="Error", status_code=500)

class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000)
    session_id: str | None = None
    patient_id: int | None = None

@app.post(API_CHAT_PATH)
@limiter.limit("15/minute")
async def chat_endpoint(request: Request, req: ChatRequest):
    # No auth: patient_id is trusted as sent by the client.
    patient_id = req.patient_id or 1
    db.log_access(patient_id, accessed_by="anonymous", endpoint="chat")
    reply, session_id = process_query_logic(req.query, patient_id, req.session_id)
    return {"response": reply, "session_id": session_id}

@app.get(API_SESSIONS_PATH)
async def get_sessions(patient_id: int = 1):
    db.log_access(patient_id, accessed_by="anonymous", endpoint="sessions")
    sessions = db.get_sessions(patient_id)
    return {"sessions": sessions}

@app.get(API_PATIENTS_PATH)
async def get_patients():
    try:
        patients = db.get_all_patients()
    except Exception as e:
        print(f"❌ /patients failed: {e}")
        raise HTTPException(status_code=500, detail="Could not load patients from the database.")
    return {"patients": patients}

@app.get(f"{API_SESSION_HISTORY_PATH}/{{session_id}}")
async def get_session_history(session_id: str, patient_id: int = 1):
    db.log_access(patient_id, accessed_by="anonymous", endpoint="session_history")
    history = db.get_full_session_history(patient_id, session_id)
    return {"history": history}

@app.get(API_GLOBAL_HISTORY_PATH)
async def get_global_history(patient_id: int = 1, days: int = 30, limit: int = 30):
    db.log_access(patient_id, accessed_by="anonymous", endpoint="global_history")
    history = db.get_global_history(patient_id, days, limit)
    return {"history": history}

@app.get(API_CONFIG_PATH)
async def get_config():
    # Intentionally minimal: this is also the Railway healthcheck target,
    # so it must stay public/unauthenticated, but it shouldn't leak
    # internal wiring (host/port/paths) to the world.
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT)
