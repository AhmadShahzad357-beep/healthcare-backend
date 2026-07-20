"""
Create (or update) a staff login account.

Usage:
    python scripts/create_staff_user.py <username> <password>

Example:
    python scripts/create_staff_user.py dr.ahmed "S0meStr0ngP@ssword!"
"""
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env", encoding="utf-8-sig")

sys.path.append(str(Path(__file__).resolve().parent.parent))
from src.auth import create_staff_user


def main():
    if len(sys.argv) != 3:
        print("Usage: python scripts/create_staff_user.py <username> <password>")
        sys.exit(1)
    username, password = sys.argv[1], sys.argv[2]
    if len(password) < 8:
        print("❌ Password must be at least 8 characters.")
        sys.exit(1)
    create_staff_user(username, password)
    print(f"✅ Staff account '{username}' created/updated.")


if __name__ == "__main__":
    main()