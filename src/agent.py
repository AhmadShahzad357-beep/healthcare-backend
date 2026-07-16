import re
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent))
import retrieval
import patient_db
import medicine_api

COMMON_DRUGS = {
    "paracetamol", "panadol", "acetaminophen", "ibuprofen", "brufen", "advil",
    "aspirin", "disprin", "ecospirin", "metformin", "insulin", "lisinopril",
    "atenolol", "verapamil", "warfarin", "amoxicillin", "azithromycin",
    "omeprazole", "levothyroxine", "atorvastatin", "simvastatin"
}

# NOTE: These are ONLY for genuine "what did we talk about before" cross-session
# chat-memory recall. Do NOT put generic words like "kab" (when), "purani" (old),
# "pichli" (last) here — those are how people normally ask about their
# appointments/lab reports (which live in the SQL database, not chat memory),
# and previously this list was swallowing those queries before they ever reached
# the patient database lookup.
HISTORY_KEYWORDS = [
    "pichli baar humne", "pichli baar maine", "last time i asked", "last time we talked",
    "previous chat", "previous conversation", "hamari baat cheet", "humne kya baat ki",
    "aapne kaha tha", "you told me earlier", "you said earlier", "chat history",
    "purani chat", "pichli guftagu", "maine pehle kya poocha"
]

# Broadened so patient queries route correctly even without an explicit pronoun,
# as long as a patient name was matched, or the question is clearly about a
# person's medical data.
PRONOUNS = ["mera", "meri", "mere", "my", "mujhe", "apna", "apni", "patient",
            "mari", "iski", "uski", "unki", "unka", "uska", "inki", "inka"]

MEDICAL_CONTEXT = [
    "report", "reports", "test", "allergy", "allergies", "history", "appointment",
    "appointments", "checkup", "check up", "blood", "sugar", "bp", "age", "umar",
    "umr", "naam", "name", "gender", "jins", "blood group", "medicine", "dawai",
    "diagnosis", "condition", "bimari", "disease", "prescription", "lab",
    "mulaqat", "doctor", "contact", "phone", "number"
]


def _load_all_patients_cached():
    if not hasattr(_load_all_patients_cached, "_cache"):
        try:
            db = patient_db.PatientDB()
            _load_all_patients_cached._cache = db.get_all_patients()
        except Exception:
            _load_all_patients_cached._cache = []
    return _load_all_patients_cached._cache


def resolve_patient_id(query: str, default_patient_id: int = 1):
    """If the query explicitly names a patient (e.g. 'Sara Tran ki age'), resolve
    to that patient's id. Otherwise fall back to the currently selected patient
    (default_patient_id, normally passed in from the frontend's patient selector)."""
    query_lower = query.lower()
    for p in _load_all_patients_cached():
        name = (p.get("name") or "").strip()
        if not name:
            continue
        if name.lower() in query_lower:
            return p["id"], True
        # also match by first name alone (e.g. "Sara" instead of "Sara Tran")
        first_name = name.split()[0].lower()
        if len(first_name) > 2 and re.search(rf"\b{re.escape(first_name)}\b", query_lower):
            return p["id"], True
    return default_patient_id, False


def is_patient_query(query: str, name_matched: bool) -> bool:
    query_lower = query.lower()
    has_pronoun = any(p in query_lower for p in PRONOUNS)
    has_medical = any(m in query_lower for m in MEDICAL_CONTEXT)
    if name_matched:
        # A specific patient was named -> almost certainly asking about that
        # patient's record, even without an explicit medical keyword
        # (e.g. "Sara Tran kaun hai?").
        return True
    return has_pronoun and has_medical


def is_history_query(query: str) -> bool:
    query_lower = query.lower()
    return any(phrase in query_lower for phrase in HISTORY_KEYWORDS)


def is_medicine_interaction_query(query: str) -> bool:
    query_lower = query.lower()
    conjunctions = ["aur", "and", "+", "&", "ke saath", "with"]
    if not any(c in query_lower for c in conjunctions):
        return False
    words = re.findall(r'[a-zA-Z]+', query_lower)
    drug_matches = [word for word in words if word in COMMON_DRUGS]
    return len(set(drug_matches)) >= 2


def route_query(query: str, patient_id: int = 1):
    print(f"\n🔍 Analyzing Query: '{query}' (Patient ID: {patient_id})")

    resolved_patient_id, name_matched = resolve_patient_id(query, patient_id)
    if name_matched and resolved_patient_id != patient_id:
        print(f"   → Detected patient name in query, using patient_id={resolved_patient_id} instead of {patient_id}")

    # 1) PATIENT-SPECIFIC SQL DATA — checked first, since this is the most
    #    common and most important intent and must not get shadowed by the
    #    chat-history branch below.
    if is_patient_query(query, name_matched):
        print("   → Intent: PATIENT_SPECIFIC (SQL)")
        db = patient_db.PatientDB()
        profile = db.get_patient_profile(resolved_patient_id)
        if profile:
            history = db.get_medical_history(resolved_patient_id)
            reports = db.get_lab_reports(resolved_patient_id, limit=5)
            apps = db.get_appointments(resolved_patient_id)
            return {
                "intent": "patient_db",
                "data": {"profile": profile, "history": history, "reports": reports, "appointments": apps},
                "message": f"Found patient: {profile['name']}",
                "found": True
            }
        else:
            return {
                "intent": "patient_db",
                "data": None,
                "message": f"Patient with ID {resolved_patient_id} not found.",
                "found": False
            }

    # 2) CROSS-SESSION CHAT MEMORY — only for genuine "what did we discuss
    #    before" recall. If nothing relevant is found, we fall through to the
    #    other intents below instead of dead-ending with "no info found".
    if is_history_query(query):
        print("   → Intent: HISTORY (Cross-session memory)")
        try:
            from retrieval_history import ChatHistoryRetriever
            retriever = ChatHistoryRetriever()
            results = retriever.search(query, resolved_patient_id, top_k=5)
            if results:
                context = "--- PAST CHATS (Semantic Search) ---\n"
                for r in results:
                    context += f"[{r['timestamp']}] User: {r['user_msg']}\nBot: {r['bot_reply']}\n\n"
                return {
                    "intent": "history_rag",
                    "data": {"context": context, "raw": results},
                    "message": f"Found {len(results)} relevant past chats.",
                    "found": True
                }
            print("   ⚠️ No past chat history found, falling through to other intents.")
        except Exception as e:
            print(f"   ⚠️ History retriever error: {e}, falling through to other intents.")

    # 3) MEDICINE INTERACTION
    if is_medicine_interaction_query(query):
        print("   → Intent: MEDICINE_INTERACTION (API)")
        words = re.findall(r'[a-zA-Z]+', query.lower())
        drugs = [word for word in words if word in COMMON_DRUGS]
        if len(drugs) >= 2:
            drug1, drug2 = drugs[0], drugs[1]
            result = medicine_api.check_medicine_interaction(drug1, drug2)
            return {"intent": "medicine_api", "data": result, "message": f"Interaction checked for {drug1} and {drug2}", "found": True}
        else:
            return {"intent": "medicine_api", "data": None, "message": "Could not identify two medicine names.", "found": False}

    # 4) GENERAL MEDICAL KNOWLEDGE (RAG over PDFs)
    print("   → Intent: GENERAL_KNOWLEDGE (RAG)")
    retriever = retrieval.MedicalRetriever()
    context_chunks = retriever.search(query)
    context_text = ""
    sources = set()
    for chunk in context_chunks:
        context_text += chunk['text'] + "\n\n"
        sources.add(chunk['source'])
    return {
        "intent": "retrieval",
        "data": {"context": context_text, "chunks": context_chunks, "sources": list(sources)},
        "message": f"Retrieved {len(context_chunks)} chunks.",
        "found": bool(context_text.strip())
    }
