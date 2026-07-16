import sqlite3
from config import DB_PATH

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# 1. Add session_id column to conversation_logs (if not exists)
try:
    cursor.execute("ALTER TABLE conversation_logs ADD COLUMN session_id TEXT")
    print("✅ Added session_id column to conversation_logs")
except sqlite3.OperationalError:
    print("ℹ️ session_id column already exists")

# 2. Create sessions table
cursor.executescript('''
    CREATE TABLE IF NOT EXISTS sessions (
        id TEXT PRIMARY KEY,
        patient_id INTEGER NOT NULL,
        title TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (patient_id) REFERENCES patients(id)
    );
''')
print("✅ Sessions table created")

conn.commit()
conn.close()
print("🎉 Database migration complete!")
