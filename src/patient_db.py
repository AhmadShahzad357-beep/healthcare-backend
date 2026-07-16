import sqlite3
from typing import List, Dict, Optional
from pathlib import Path
import sys
import uuid
sys.path.append(str(Path(__file__).resolve().parent.parent))
from config import DB_PATH

class PatientDB:
    def __init__(self):
        self.db_path = DB_PATH

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def verify_patient(self, patient_id: int, name: str = None) -> bool:
        conn = self._get_connection()
        cursor = conn.cursor()
        if name:
            cursor.execute("SELECT id FROM patients WHERE id = ? AND name LIKE ?", (patient_id, f"%{name}%"))
        else:
            cursor.execute("SELECT id FROM patients WHERE id = ?", (patient_id,))
        result = cursor.fetchone()
        conn.close()
        return result is not None

    def get_patient_profile(self, patient_id: int) -> Optional[Dict]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, age, gender, contact, blood_group, allergies FROM patients WHERE id = ?", (patient_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return {"id": row[0], "name": row[1], "age": row[2], "gender": row[3], "contact": row[4], "blood_group": row[5], "allergies": row[6]}
        return None

    def get_medical_history(self, patient_id: int) -> List[Dict]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT condition, diagnosed_date, status FROM medical_history WHERE patient_id = ? ORDER BY diagnosed_date DESC", (patient_id,))
        rows = cursor.fetchall()
        conn.close()
        return [{"condition": row[0], "diagnosed_date": row[1], "status": row[2]} for row in rows]

    def get_lab_reports(self, patient_id: int, limit: int = 5) -> List[Dict]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT test_name, result, unit, date, raw_text FROM lab_reports WHERE patient_id = ? ORDER BY date DESC LIMIT ?", (patient_id, limit))
        rows = cursor.fetchall()
        conn.close()
        return [{"test_name": row[0], "result": row[1], "unit": row[2], "date": row[3], "raw_text": row[4]} for row in rows]

    def get_appointments(self, patient_id: int) -> List[Dict]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT doctor_name, department, date, time, status FROM appointments WHERE patient_id = ? ORDER BY date DESC", (patient_id,))
        rows = cursor.fetchall()
        conn.close()
        return [{"doctor": row[0], "department": row[1], "date": row[2], "time": row[3], "status": row[4]} for row in rows]

    def search_patients_by_name(self, name: str) -> List[Dict]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, age, contact FROM patients WHERE name LIKE ? LIMIT 10", (f"%{name}%",))
        rows = cursor.fetchall()
        conn.close()
        return [{"id": row[0], "name": row[1], "age": row[2], "contact": row[3]} for row in rows]

    def get_all_patients(self) -> List[Dict]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, age FROM patients ORDER BY name")
        rows = cursor.fetchall()
        conn.close()
        return [{"id": row[0], "name": row[1], "age": row[2]} for row in rows]

    def create_session(self, patient_id: int, title: str = "New Chat") -> str:
        session_id = str(uuid.uuid4())[:8]
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                patient_id INTEGER NOT NULL,
                title TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (patient_id) REFERENCES patients(id)
            )
        ''')
        try:
            cursor.execute("ALTER TABLE conversation_logs ADD COLUMN session_id TEXT")
        except sqlite3.OperationalError:
            pass
        cursor.execute(
            "INSERT INTO sessions (id, patient_id, title) VALUES (?, ?, ?)",
            (session_id, patient_id, title)
        )
        conn.commit()
        conn.close()
        return session_id

    def get_sessions(self, patient_id: int) -> List[Dict]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, title, created_at FROM sessions WHERE patient_id = ? ORDER BY created_at DESC",
            (patient_id,)
        )
        rows = cursor.fetchall()
        conn.close()
        return [{"id": row[0], "title": row[1], "created_at": row[2]} for row in rows]

    def get_session_history(self, patient_id: int, session_id: str, limit: int = 10) -> List[Dict]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT user_msg, bot_reply FROM conversation_logs WHERE patient_id = ? AND session_id = ? ORDER BY timestamp DESC LIMIT ?",
            (patient_id, session_id, limit)
        )
        rows = cursor.fetchall()
        conn.close()
        history = []
        for user_msg, bot_reply in reversed(rows):
            history.append({"user": user_msg, "bot": bot_reply})
        return history

    def save_conversation_with_session(self, patient_id: int, session_id: str, user_msg: str, bot_reply: str):
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM sessions WHERE id = ?", (session_id,))
        if not cursor.fetchone():
            cursor.execute(
                "INSERT INTO sessions (id, patient_id, title) VALUES (?, ?, ?)",
                (session_id, patient_id, user_msg[:30] + "...")
            )
        cursor.execute(
            "INSERT INTO conversation_logs (patient_id, session_id, user_msg, bot_reply, timestamp) VALUES (?, ?, ?, ?, datetime('now'))",
            (patient_id, session_id, user_msg, bot_reply)
        )
        cursor.execute(
            "UPDATE sessions SET title = ? WHERE id = ? AND title = 'New Chat'",
            (user_msg[:30] + "...", session_id)
        )
        conn.commit()
        conn.close()

    def get_full_session_history(self, patient_id: int, session_id: str) -> List[Dict]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT user_msg, bot_reply FROM conversation_logs WHERE patient_id = ? AND session_id = ? ORDER BY timestamp ASC",
            (patient_id, session_id)
        )
        rows = cursor.fetchall()
        conn.close()
        return [{"user": row[0], "bot": row[1]} for row in rows]

    def get_global_history(self, patient_id: int, time_days: int = 7, limit: int = 20) -> List[Dict]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT user_msg, bot_reply, timestamp, session_id 
            FROM conversation_logs 
            WHERE patient_id = ? 
            AND timestamp >= datetime('now', ?) 
            ORDER BY timestamp DESC 
            LIMIT ?
            """,
            (patient_id, f'-{time_days} days', limit)
        )
        rows = cursor.fetchall()
        conn.close()
        return [{"user": row[0], "bot": row[1], "time": row[2], "session": row[3]} for row in rows]
