"""
Create (or reset) the login account for one existing patient record.

Each patient_id gets exactly one login. Running this again for the same
patient_id replaces that patient's username/password rather than creating
a second account linked to the same record.

Usage:
    python scripts/create_patient_user.py <patient_id> <username> <password>

Example:
    python scripts/create_patient_user.py 42 jane.doe "S0meStr0ngP@ssword!"
"""
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env", encoding="utf-8-sig")

sys.path.append(str(Path(__file__).resolve().parent.parent))
from src.auth import create_patient_user
from src.patient_db import PatientDB


def main():
    if len(sys.argv) != 4:
        print("Usage: python scripts/create_patient_user.py <patient_id> <username> <password>")
        sys.exit(1)

    try:
        patient_id = int(sys.argv[1])
    except ValueError:
        print("❌ patient_id must be an integer.")
        sys.exit(1)

    username, password = sys.argv[2], sys.argv[3]
    if len(password) < 8:
        print("❌ Password must be at least 8 characters.")
        sys.exit(1)

    db = PatientDB()
    profile = db.get_patient_profile(patient_id)
    if not profile:
        print(f"❌ No patient found with patient_id={patient_id}. Create the patient record first.")
        sys.exit(1)

    create_patient_user(patient_id, username, password)
    print(f"✅ Patient login '{username}' created/updated for patient_id={patient_id} ({profile.get('name', '')}).")


if __name__ == "__main__":
    main()
