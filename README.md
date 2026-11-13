# Clinic Booking API & Web Portal (Koya Cohort 4 Assessment)

A assessment demo appointment booking API and patient web interface built with **FastAPI**, **PostgreSQL** (Neon / Docker), and **Pydantic**, satisfying all 5 levels of the [Koya Assessment Specification](https://koyaacademy.com/assessment-api).

---

## API reference

Open `/docs` on the running service for interactive Swagger UI, `/redoc` for the reference, or `/openapi.json` for the machine-readable schema. In Swagger UI, click **Authorize** and enter the configured API key to try the assessment endpoints. The health check at `/health` is public.

## 🌟 Architecture & Level Breakdown

### **Level 1 · Core Booking Flow**
- **`POST /reset`**: Replaces all slots with the provided array and resets previous bookings, idempotency logs, and rate limit counters.
- **`GET /slots`**: Returns all slots ordered by earliest `start` time first. Supports `?provider=<name>` exact match filtering. Each slot includes `available: true/false` (`false` whenever an active confirmed booking exists).
- **`POST /bookings`**: Creates a booking and returns `201 Created` with status `confirmed`.
- **`GET /bookings/{id}`**: Retrieves a booking by its unique identifier, returning `404` if not found.

### **Level 2 · Security & Input Validation**
- **Security (`X-API-Key`)**: All assessment endpoints require the `X-API-Key` header. Requests with a missing or incorrect key are rejected with `401 Unauthorized` (`{"error": "..."}`).
- **Data Sanitization**: Pydantic validators automatically trim leading/trailing whitespace from `name` and `email`, and store `email` in lowercase.
- **Strict Validation**: Returns `400 Bad Request` if `slot_id`, `name`, or `email` is missing or empty, or if the email format is invalid.
- **Slot Time Guard**: Returns `400 Bad Request` if the target slot has already started (`slot.start <= now()`).
- **Slot Existence**: Returns `404 Not Found` if the slot does not exist.
- **Error Formatting**: Every single error response strictly follows the JSON format `{"error": "<message>"}`.

### **Level 3 · Concurrency & Cancellation**
- **Atomic Concurrency Guarantee**: Two requests arriving at the exact same millisecond can **never** double-book a slot. We enforce this at the database level with a PostgreSQL partial unique index:
  ```sql
  CREATE UNIQUE INDEX idx_confirmed_slot ON bookings (slot_id) WHERE status = 'confirmed';
  ```
  Even under high concurrent load, exactly one transaction commits; all others trigger a conflict and immediately return `409 Conflict` (`{"error": "Slot already booked"}`).
- **`DELETE /bookings/{id}`**: Sets booking `status` to `cancelled`, freeing the slot immediately.
  - If the booking does not exist: returns `404 Not Found`.
  - If the booking is already cancelled: returns `409 Conflict` (`{"error": "Already cancelled"}`).

### **Level 4 · Idempotency & Cursor Pagination**
- **Idempotent Requests**: Clients can optionally provide an `Idempotency-Key` header on `POST /bookings`.
  - Retrying with the **same key and identical request body** returns the exact original response (same status code, same booking `id`) without creating duplicate records.
  - Reusing the **same key with a different request body** returns `422 Unprocessable Entity`.
- **Cursor-Based Pagination (`GET /bookings`)**:
  - Lists a patient's bookings ordered oldest first (`created_at ASC, id ASC`).
  - Query parameters: `email` (required, case-insensitive), `limit` (optional, 1 to 50, default 10; invalid values return `400 Bad Request`), and `cursor` (optional opaque Base64 token).
  - Returns `{"bookings": [...], "next_cursor": "..." | null}`.

### **Level 5 · Anti-Spam Rate Limiting**
- **Sliding-Window Protection**: Limits bookings to at most **5 attempts per email per minute** (failed attempts count too).
- The 6th attempt within the 60-second window is rejected with **`429 Too Many Requests`** and includes a **`Retry-After: <seconds>`** header indicating whole seconds until the oldest attempt expires.
- Other email addresses remain completely unaffected.

---

## 💻 Patient Web Portal

The application serves a modern, responsive web application at the root URL (`/`):
- **Browse & Filter Slots**: Real-time view of available slots with specialist filter (`Dr Ade`, `Dr Fatima`, etc.).
- **Book Instantly**: Clean booking form with instant validation, loading feedback, and confirmation view.
- **My Appointments Tab**: Lookup bookings by email with **Level 4 cursor pagination** ("Load More") and **Level 3 cancellation** ("Cancel Appointment").
- **Interactive Demos**: Enter the configured assessment key from the API Key button. The page retains it for the browser session. Use "Quick Reset Demo Slots" to initialize demo data before recording. Reset clears all bookings.

---

## 🚀 Local Development & Testing

### 1. Prerequisites
- Python 3.12+
- Docker (for local PostgreSQL on port 5433)

### 2. Setup
```bash
# Clone the repository
git clone https://github.com/solomonayodeleo/koya-clinic-booking-api.git
cd koya-clinic-booking-api

# Create and activate virtual environment
uv venv
source .venv/bin/activate

# Install dependencies
uv pip install -r requirements.txt
```

### 3. Run Automated Tests
All 5 levels and concurrency race conditions are verified by pytest:
```bash
DATABASE_URL=postgresql://postgres:postgres@localhost:5433/clinic_booking_test API_KEY=local-test-key pytest -v
```

Create the dedicated test database first. The test suite resets its contents.

### 4. Start the Application Locally
```bash
uvicorn app.main:app --port 8080 --reload
```
Open [http://localhost:8080](http://localhost:8080) in your browser to interact with the patient web page!

---

## ☁️ Deployment Guide (Render)

1. Push this repository to GitHub: `solomonayodeleo/koya-clinic-booking-api`.
2. On [Render Dashboard](https://dashboard.render.com):
   - Click **New +** → **Web Service**.
   - Select your GitHub repository.
   - **Environment**: `Python`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
3. Add Environment Variables:
   - `DATABASE_URL`: Your Neon PostgreSQL connection string (`postgresql://...sslmode=require`).
   - `API_KEY`: A private random value (generate with `openssl rand -hex 32`)
   - `PYTHON_VERSION`: `3.12.6`
4. Click **Create Web Service**. Your API and Web UI will be live at `https://<your-service>.onrender.com`!

---

## 🎥 5-Minute Loom Walkthrough Guide

Use this outline when recording your video:
1. **Introduction (30s)**: Introduce yourself, the project, and state the tech stack (FastAPI + PostgreSQL + Pydantic).
2. **Web Page Demo (1.5 min)**:
   - Show available appointment slots on the web interface.
   - Book a slot: show validation, instant booking, and the confirmation screen.
   - Switch to "My Appointments", search by email, show the confirmed booking, and demonstrate cancelling it (freeing the slot).
3. **Code Architecture (2 min)**:
   - Show `app/routers/bookings.py`: highlight how **Level 3** prevents race conditions via the database partial unique index (`idx_confirmed_slot`).
   - Highlight **Level 4** idempotency (`Idempotency-Key` comparison) and cursor pagination.
   - Highlight **Level 5** sliding-window rate limiting per email with the `Retry-After` header.
4. **Automated Test Suite (1 min)**:
   - Run `pytest -v` in the terminal to show all 5 levels passing automated tests with green checks!
