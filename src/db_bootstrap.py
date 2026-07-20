"""
Safe, idempotent database bootstrap.

Root cause this fixes: `healthcare.db` is in .gitignore and was never
committed anywhere, and scripts/seed_database.py (which creates the
`patients` table) was intentionally removed from Railway's startCommand
because it's destructive (DROPs tables every run). Net effect: on a fresh
deploy (Railway, or any fresh clone) the `patients` table simply doesn't
exist, so every route that touches it (most importantly GET /patients,
which the frontend's patient dropdown depends on) throws an unhandled
sqlite3.OperationalError: no such table: patients -> the client sees this
as a broken/unreachable-looking API.

This module runs once at API startup and:
  1. Creates all required tables with CREATE TABLE IF NOT EXISTS (never drops
     anything, so it's 100% safe to run on every restart/redeploy).
  2. ONLY inserts demo patients if the `patients` table is currently EMPTY.
     If you already have real data, this is a no-op.

This makes the app self-healing on platforms like Railway where the
filesystem is ephemeral and nobody has shell access to run a seed script
by hand after every deploy.
"""
import random
import sqlite3
from pathlib import Path

from faker import Faker

from config import DB_PATH

CONDITIONS = [
    "Type 2 Diabetes", "Hypertension", "Asthma", "High Cholesterol",
    "Thyroid", "Migraine", "Arthritis", "Gastritis", "Anemia", "Depression",
]
LAB_TESTS = [
    ("Blood Sugar (Fasting)", "mg/dL", 70, 100),
    ("Blood Sugar (Random)", "mg/dL", 80, 140),
    ("Cholesterol (Total)", "mg/dL", 125, 200),
    ("LDL Cholesterol", "mg/dL", 0, 100),
    ("HDL Cholesterol", "mg/dL", 40, 60),
    ("Triglycerides", "mg/dL", 50, 150),
    ("Hemoglobin", "g/dL", 13, 17),
    ("Creatinine", "mg/dL", 0.7, 1.3),
    ("Uric Acid", "mg/dL", 3.4, 7.0),
    ("Vitamin D", "ng/mL", 30, 80),
]
ALLERGIES = ["Penicillin", "Sulfa", "Aspirin", "Codeine", "Latex", "Peanuts", "Dust", "Pollen"]
DOCTORS = ["Dr. Usman", "Dr. Fatima", "Dr. Ali", "Dr. Sara", "Dr. Ahmed"]
DEPARTMENTS = ["Cardiology", "Neurology", "Orthopedics", "ENT", "General Medicine", "Dermatology"]


def _create_tables(cursor: sqlite3.Cursor) -> None:
    cursor.executescript(
        """
        CREATE TABLE IF NOT EXISTS patients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            age INTEGER,
            gender TEXT,
            contact TEXT,
            blood_group TEXT,
            allergies TEXT
        );

        CREATE TABLE IF NOT EXISTS medical_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            condition TEXT,
            diagnosed_date TEXT,
            status TEXT,
            FOREIGN KEY (patient_id) REFERENCES patients(id)
        );

        CREATE TABLE IF NOT EXISTS lab_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            test_name TEXT,
            result REAL,
            unit TEXT,
            date TEXT,
            raw_text TEXT,
            FOREIGN KEY (patient_id) REFERENCES patients(id)
        );

        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            doctor_name TEXT,
            department TEXT,
            date TEXT,
            time TEXT,
            status TEXT,
            FOREIGN KEY (patient_id) REFERENCES patients(id)
        );

        CREATE TABLE IF NOT EXISTS conversation_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            session_id TEXT,
            user_msg TEXT,
            bot_reply TEXT,
            timestamp TEXT
        );

        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            patient_id INTEGER NOT NULL,
            title TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (patient_id) REFERENCES patients(id)
        );

        CREATE TABLE IF NOT EXISTS access_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            accessed_by TEXT NOT NULL,
            endpoint TEXT NOT NULL,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """
    )


def _seed_demo_patients(cursor: sqlite3.Cursor, num: int = 150) -> None:
    fake = Faker()
    patient_ids = []
    for _ in range(num):
        gender = random.choice(["Male", "Female"])
        age = random.randint(18, 80)
        allergy_list = random.sample(ALLERGIES, k=random.randint(0, 2))
        allergies_str = ", ".join(allergy_list) if allergy_list else "None"
        cursor.execute(
            """INSERT INTO patients (name, age, gender, contact, blood_group, allergies)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                fake.name(),
                age,
                gender,
                fake.phone_number(),
                random.choice(["A+", "A-", "B+", "B-", "O+", "O-", "AB+", "AB-"]),
                allergies_str,
            ),
        )
        patient_ids.append(cursor.lastrowid)

    for pid in patient_ids:
        for condition in random.sample(CONDITIONS, random.randint(1, 3)):
            diagnosed_date = fake.date_between(start_date="-10y", end_date="today")
            status = random.choice(["Active", "Managed", "Resolved", "Under Treatment"])
            cursor.execute(
                """INSERT INTO medical_history (patient_id, condition, diagnosed_date, status)
                   VALUES (?, ?, ?, ?)""",
                (pid, condition, diagnosed_date, status),
            )

        for _ in range(random.randint(3, 8)):
            test_name, unit, min_val, max_val = random.choice(LAB_TESTS)
            result = round(random.uniform(min_val * 0.8, max_val * 1.2), 2)
            report_date = fake.date_between(start_date="-2y", end_date="today")
            raw_text = f"{test_name}: {result} {unit} (Normal range: {min_val}-{max_val} {unit}). Tested on {report_date}."
            cursor.execute(
                """INSERT INTO lab_reports (patient_id, test_name, result, unit, date, raw_text)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (pid, test_name, result, unit, report_date, raw_text),
            )

        for _ in range(random.randint(2, 5)):
            doctor = random.choice(DOCTORS)
            dept = random.choice(DEPARTMENTS)
            app_date = fake.date_between(start_date="-30d", end_date="+60d")
            app_time = random.choice(["09:00 AM", "10:00 AM", "11:00 AM", "02:00 PM", "03:00 PM", "04:00 PM"])
            status = random.choice(["Scheduled", "Completed", "Cancelled", "Missed"])
            cursor.execute(
                """INSERT INTO appointments (patient_id, doctor_name, department, date, time, status)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (pid, doctor, dept, app_date, app_time, status),
            )


def ensure_database_ready() -> None:
    """Call once at API startup. Safe to call every time the process boots."""
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.cursor()
        _create_tables(cursor)
        conn.commit()

        cursor.execute("SELECT COUNT(*) FROM patients")
        count = cursor.fetchone()[0]
        if count == 0:
            print("ℹ️  patients table is empty — seeding 150 demo patients so the app is usable out of the box...")
            _seed_demo_patients(cursor, num=150)
            conn.commit()
            print("✅ Demo data seeded.")
        else:
            print(f"✅ Database OK — {count} patients already present, leaving data as-is.")
    finally:
        conn.close()
