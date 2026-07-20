import jwt
import os
import sqlite3
import bcrypt
from datetime import datetime, timedelta
from pathlib import Path
from fastapi import HTTPException, Depends, Header
import sys
sys.path.append(str(Path(__file__).resolve().parent.parent))
from config import DB_PATH

# No insecure default: if JWT_SECRET_KEY is missing, fail loudly at import
# time instead of silently signing tokens with a well-known placeholder
# string that anyone reading this codebase could use to forge a valid
# login for any account.
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError(
        "JWT_SECRET_KEY is not set. Generate one with:\n"
        "    python -c \"import secrets; print(secrets.token_hex(32))\"\n"
        "and put it in your .env file as JWT_SECRET_KEY=<the value>."
    )

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 1 day


def hash_password(password: str) -> str:
    # bcrypt has a hard 72-byte input limit; truncate defensively so a very
    # long password doesn't raise instead of just being (safely) capped.
    pw_bytes = password.encode("utf-8")[:72]
    return bcrypt.hashpw(pw_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    pw_bytes = plain_password.encode("utf-8")[:72]
    return bcrypt.checkpw(pw_bytes, hashed_password.encode("utf-8"))


def create_access_token(data: dict, expires_delta: timedelta = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def get_current_user(authorization: str | None = Header(default=None)) -> dict:
    """FastAPI dependency: require a valid 'Authorization: Bearer <token>'
    header on any route that uses this. Raises 401 if missing/invalid."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = authorization.split(" ", 1)[1]
    return decode_token(token)


# --- Two account types: staff and patient ---------------------------------
# - Staff accounts: can look up ANY patient_id (clinic/receptionist/doctor
#   use case). Token carries role="staff".
# - Patient accounts: tied to exactly one patient_id at creation time.
#   Token carries role="patient" and patient_id=<that id>. A patient token
#   can only ever be used to read that one patient's data -- enforced by
#   authorize_patient_access() below, called from every route in api.py
#   that takes a patient_id.

def _get_connection():
    return sqlite3.connect(DB_PATH)


def ensure_staff_table():
    conn = _get_connection()
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS staff_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()


def create_staff_user(username: str, password: str):
    ensure_staff_table()
    conn = _get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO staff_users (username, password_hash) VALUES (?, ?)",
        (username, hash_password(password)),
    )
    conn.commit()
    conn.close()


def authenticate_staff(username: str, password: str) -> bool:
    ensure_staff_table()
    conn = _get_connection()
    cur = conn.cursor()
    cur.execute("SELECT password_hash FROM staff_users WHERE username = ?", (username,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return False
    return verify_password(password, row[0])


def ensure_patient_users_table():
    conn = _get_connection()
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS patient_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER UNIQUE NOT NULL,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (patient_id) REFERENCES patients (id)
        )
    ''')
    conn.commit()
    conn.close()


def create_patient_user(patient_id: int, username: str, password: str):
    """Create (or reset) the login for one patient. One account per
    patient_id -- a second call with the same patient_id replaces the
    existing account rather than creating a way to link two logins to one
    patient record."""
    ensure_patient_users_table()
    conn = _get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO patient_users (patient_id, username, password_hash)
           VALUES (?, ?, ?)
           ON CONFLICT(patient_id) DO UPDATE SET
               username = excluded.username,
               password_hash = excluded.password_hash""",
        (patient_id, username, hash_password(password)),
    )
    conn.commit()
    conn.close()


def authenticate_patient(username: str, password: str) -> int | None:
    """Returns the patient_id on success, None on failure. Never trust a
    patient_id the caller sends at login time -- it's looked up from the
    username/password only."""
    ensure_patient_users_table()
    conn = _get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT patient_id, password_hash FROM patient_users WHERE username = ?",
        (username,),
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    patient_id, password_hash = row
    if not verify_password(password, password_hash):
        return None
    return patient_id


def get_current_staff(user: dict = Depends(get_current_user)) -> dict:
    """FastAPI dependency: require the token to belong to a staff account.
    Use this on routes that must never be reachable by a patient token at
    all (e.g. listing every patient)."""
    if user.get("role") != "staff":
        raise HTTPException(status_code=403, detail="Staff access required")
    return user


def authorize_patient_access(patient_id: int, user: dict):
    """Call this from every route that reads/writes a specific patient_id.
    - Staff tokens: allowed to access any patient_id.
    - Patient tokens: allowed ONLY when patient_id matches the id baked
      into their own token at login time -- the value the client sends in
      the request is never trusted on its own for patient-role tokens.
    """
    if user.get("role") == "staff":
        return
    if user.get("role") == "patient" and user.get("patient_id") == patient_id:
        return
    raise HTTPException(status_code=403, detail="Not authorized for this patient record")
