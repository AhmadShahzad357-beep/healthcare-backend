import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "data"
PDFS_DIR = DATA_DIR / "pdfs"
STATIC_KNOWLEDGE_DIR = DATA_DIR / "static_knowledge"
CHROMA_DIR = Path(os.getenv("CHROMA_DIR", str(BASE_DIR / "chroma_db"))).resolve()
DB_PATH = Path(os.getenv("DB_PATH", str(BASE_DIR / "healthcare.db"))).resolve()

HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))
API_BASE_URL = os.getenv("API_BASE_URL", "")
API_CONFIG_PATH = os.getenv("API_CONFIG_PATH", "/config")
API_CHAT_PATH = os.getenv("API_CHAT_PATH", "/chat")
API_PATIENTS_PATH = os.getenv("API_PATIENTS_PATH", "/patients")
API_SESSIONS_PATH = os.getenv("API_SESSIONS_PATH", "/sessions")
API_SESSION_HISTORY_PATH = os.getenv("API_SESSION_HISTORY_PATH", "/session_history")
API_GLOBAL_HISTORY_PATH = os.getenv("API_GLOBAL_HISTORY_PATH", "/global_history")
API_WHATSAPP_PATH = os.getenv("API_WHATSAPP_PATH", "/whatsapp")

EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
TOP_K = 5
SIMILARITY_THRESHOLD = 0.35

LLM_PROVIDER = "groq"
GROQ_MODEL = "llama-3.1-8b-instant"
TEMPERATURE = 0.1
MAX_TOKENS = 512

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "your-groq-api-key-here")
OPENFDA_API_KEY = os.getenv("OPENFDA_API_KEY", "")
OPENFDA_LABEL_URL = os.getenv("OPENFDA_LABEL_URL", "https://api.fda.gov/drug/label.json")

APPOINTMENT_SLOTS = ["09:00 AM", "10:00 AM", "11:00 AM", "02:00 PM", "03:00 PM", "04:00 PM"]
DOCTORS_LIST = ["Dr. Usman", "Dr. Fatima", "Dr. Ali", "Dr. Sara", "Dr. Ahmed"]
