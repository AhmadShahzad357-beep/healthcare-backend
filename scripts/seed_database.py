"""
⚠️  DANGER: this script DROPS and recreates the patients, medical_history,
lab_reports, appointments, and conversation_logs tables, replacing them
with fresh fake (Faker-generated) data.

Run this manually, ONLY when you actually want to reset/reseed demo data:
    python scripts/seed_database.py

NEVER wire this into an automatic deploy/start command (it used to be in
railway.json's startCommand -- that has been removed on purpose). Doing so
would silently destroy all real patient data and chat history on every
restart/redeploy.
"""
import sqlite3
import random
from datetime import datetime, timedelta
from faker import Faker

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from config import DB_PATH

fake = Faker()

CONDITIONS = [
    "Type 2 Diabetes", "Hypertension", "Asthma", "High Cholesterol",
    "Thyroid", "Migraine", "Arthritis", "Gastritis", "Anemia", "Depression"
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
    ("Vitamin D", "ng/mL", 30, 80)
]

ALLERGIES = ["Penicillin", "Sulfa", "Aspirin", "Codeine", "Latex", "Peanuts", "Dust", "Pollen"]
DOCTORS = ["Dr. Usman", "Dr. Fatima", "Dr. Ali", "Dr. Sara", "Dr. Ahmed"]
DEPARTMENTS = ["Cardiology", "Neurology", "Orthopedics", "ENT", "General Medicine", "Dermatology"]

def create_tables(cursor):
    cursor.executescript('''
        DROP TABLE IF EXISTS patients;
        DROP TABLE IF EXISTS medical_history;
        DROP TABLE IF EXISTS lab_reports;
        DROP TABLE IF EXISTS appointments;
        DROP TABLE IF EXISTS conversation_logs;

        CREATE TABLE patients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            age INTEGER,
            gender TEXT,
            contact TEXT,
            blood_group TEXT,
            allergies TEXT
        );

        CREATE TABLE medical_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            condition TEXT,
            diagnosed_date TEXT,
            status TEXT,
            FOREIGN KEY (patient_id) REFERENCES patients(id)
        );

        CREATE TABLE lab_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            test_name TEXT,
            result REAL,
            unit TEXT,
            date TEXT,
            raw_text TEXT,
            FOREIGN KEY (patient_id) REFERENCES patients(id)
        );

        CREATE TABLE appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            doctor_name TEXT,
            department TEXT,
            date TEXT,
            time TEXT,
            status TEXT,
            FOREIGN KEY (patient_id) REFERENCES patients(id)
        );

        CREATE TABLE conversation_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            user_msg TEXT,
            bot_reply TEXT,
            timestamp TEXT
        );
    ''')
    print("Tables created successfully.")

def generate_patients(cursor, num=150):
    patients = []
    for _ in range(num):
        gender = random.choice(["Male", "Female"])
        age = random.randint(18, 80)
        allergy_list = random.sample(ALLERGIES, k=random.randint(0, 2))
        allergies_str = ", ".join(allergy_list) if allergy_list else "None"
        
        cursor.execute('''
            INSERT INTO patients (name, age, gender, contact, blood_group, allergies)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            fake.name(),
            age,
            gender,
            fake.phone_number(),
            random.choice(["A+", "A-", "B+", "B-", "O+", "O-", "AB+", "AB-"]),
            allergies_str
        ))
        patients.append(cursor.lastrowid)
    return patients

def generate_history(cursor, patient_ids):
    for pid in patient_ids:
        num_conditions = random.randint(1, 3)
        selected = random.sample(CONDITIONS, num_conditions)
        for condition in selected:
            diagnosed_date = fake.date_between(start_date='-10y', end_date='today')
            status = random.choice(["Active", "Managed", "Resolved", "Under Treatment"])
            cursor.execute('''
                INSERT INTO medical_history (patient_id, condition, diagnosed_date, status)
                VALUES (?, ?, ?, ?)
            ''', (pid, condition, diagnosed_date, status))

def generate_lab_reports(cursor, patient_ids):
    for pid in patient_ids:
        num_reports = random.randint(3, 8)
        for _ in range(num_reports):
            test_name, unit, min_val, max_val = random.choice(LAB_TESTS)
            result = round(random.uniform(min_val * 0.8, max_val * 1.2), 2)
            report_date = fake.date_between(start_date='-2y', end_date='today')
            raw_text = f"{test_name}: {result} {unit} (Normal range: {min_val}-{max_val} {unit}). Tested on {report_date}."
            cursor.execute('''
                INSERT INTO lab_reports (patient_id, test_name, result, unit, date, raw_text)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (pid, test_name, result, unit, report_date, raw_text))

def generate_appointments(cursor, patient_ids):
    for pid in patient_ids:
        num_appointments = random.randint(2, 5)
        for _ in range(num_appointments):
            doctor = random.choice(DOCTORS)
            dept = random.choice(DEPARTMENTS)
            app_date = fake.date_between(start_date='-30d', end_date='+60d')
            app_time = random.choice(["09:00 AM", "10:00 AM", "11:00 AM", "02:00 PM", "03:00 PM", "04:00 PM"])
            status = random.choice(["Scheduled", "Completed", "Cancelled", "Missed"])
            cursor.execute('''
                INSERT INTO appointments (patient_id, doctor_name, department, date, time, status)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (pid, doctor, dept, app_date, app_time, status))

def seed_database():
    print(f"Seeding database at: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    create_tables(cursor)
    print("Generating 150 patients...")
    patient_ids = generate_patients(cursor, num=150)
    print("Generating medical history...")
    generate_history(cursor, patient_ids)
    print("Generating lab reports...")
    generate_lab_reports(cursor, patient_ids)
    print("Generating appointments...")
    generate_appointments(cursor, patient_ids)
    
    conn.commit()
    conn.close()
    print("Database seeding complete! 150 patients are ready.")

if __name__ == "__main__":
    seed_database()
