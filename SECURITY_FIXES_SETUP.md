# Security Fixes Applied — Setup Guide

All issues from the security audit have been fixed. Here's what changed
and the extra setup steps needed because of them.

## What was fixed

1. **Auto-seed data wipe removed** from `railway.json` — seeding is now a
   manual, one-time step (`python scripts/seed_database.py`), never part
   of the automatic deploy/start command.
2. **Real authentication added, with two roles** — `/auth/login` issues a
   JWT for either a **staff** account (can look up any `patient_id`) or a
   **patient** account (locked to the one `patient_id` it was created
   for). Every route that touches patient data now requires
   `Authorization: Bearer <token>`, and every route that takes a
   `patient_id` calls `authorize_patient_access()`, which rejects a
   patient token trying to read any record other than its own — no
   matter what `patient_id` the client sends. `/patients` (the full
   directory) is staff-only regardless. The JWT secret has no insecure
   fallback anymore — the app refuses to start without `JWT_SECRET_KEY`
   set.
3. **CORS locked down** — no more silent `*` default. You must set
   `ALLOWED_ORIGINS` explicitly (defaults to `localhost:3000` for local
   dev only).
4. **Frontend `.gitignore` added** + backend secrets removed from
   `frontend/.env.local.example` (it only needs `NEXT_PUBLIC_API_URL`
   now).
5. **Twilio webhook signature verification** added (set
   `TWILIO_AUTH_TOKEN` to enable it).
6. **Errors sanitized** — raw exceptions are logged server-side only; the
   client gets a generic message.
7. **Rate limiting added** (`slowapi`) — `/chat` 15/min, `/auth/login`
   5/min, `/whatsapp` 20/min per IP.
8. **Input length limits** added on `query`, `username`, `password`.
9. **`/config` endpoint** now returns only `{"status": "ok"}`.
10. **Audit logging added** — every patient-data read is logged
    (`access_log` table: who, which patient, which endpoint, when).
11. **Cache TTL reduced** to 10 minutes (was 1 hour) for PHI-containing
    cached responses.
12. **`medicine_api.py`** now validates drug-name input and logs errors
    instead of silently swallowing them.

## New setup steps (PowerShell)

```powershell
# 1. Install dependencies (now includes pyjwt, bcrypt, slowapi)
pip install -r requirements.txt

# 2. Copy the env template and fill it in
copy .env.example .env
```

Open `.env` and set:
```
GROQ_API_KEY=your_real_key
JWT_SECRET_KEY=<paste output of the command below>
ALLOWED_ORIGINS=http://localhost:3000
```
Generate a real secret:
```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

```powershell
# 3. Seed the database (only needed once, or whenever you want to reset demo data)
python scripts\seed_database.py

# 4. Create a staff login account
python scripts\create_staff_user.py yourname "YourStrongPassword123"

# 4b. (Optional) Create a patient login for one existing patient record.
#     patient_id must already exist (e.g. from the seed data / patients table).
#     One account per patient_id -- running this again for the same id
#     resets that patient's username/password.
python scripts\create_patient_user.py 1 jane.doe "AnotherStrongPassword123"

# 5. Download the embedding model once (if not done already)
python scripts\download_models.py

# 6. Start the backend
python -m uvicorn api:app --host 127.0.0.1 --port 8000
```

Frontend (in the `frontend/` folder, separate terminal):
```powershell
copy .env.local.example .env.local
npm install
npm run dev
```
Open **http://localhost:3000** — you'll land on `/login` first now. Sign
in with either the staff account (step 4) or a patient account (step 4b)
— both use the same login form; the backend figures out which kind it is
and the frontend adapts:
- **Staff**: sees the patient-switcher dropdown, can pick any patient.
- **Patient**: no dropdown — locked to their own record, matching what
  the backend already enforces.

## Notes

- If you ever get a `401 Missing or invalid Authorization header`, your
  frontend session expired or you're not logged in — go to `/login`.
- The `/patients`, `/chat`, `/sessions`, `/session_history`, and
  `/global_history` endpoints all now require a valid login token, and
  all but `/patients` (staff-only) also enforce that a patient token can
  only ever touch its own `patient_id`.
- Set `TWILIO_AUTH_TOKEN` in `.env` before exposing `/whatsapp`
  publicly — without it, the webhook logs a loud warning and accepts
  unverified requests.
