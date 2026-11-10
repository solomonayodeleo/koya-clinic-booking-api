import base64
from datetime import datetime, timezone
import json
import math
import time
import uuid
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from psycopg.errors import UniqueViolation
from app.auth import verify_api_key
from app.database import get_connection
from app.models import Booking, NewBooking, PaginatedBookings

router = APIRouter(prefix="/bookings", tags=["Bookings"], dependencies=[Depends(verify_api_key)])

def canonical_body_hash(data: dict) -> str:
    return json.dumps(data, sort_keys=True)

@router.post("", status_code=status.HTTP_201_CREATED, response_model=Booking)
async def create_booking(
    payload: NewBooking,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    body_dict = payload.model_dump(mode="json")
    current_body_hash = canonical_body_hash(body_dict)

    async with get_connection() as conn:
        async with conn.cursor() as cur:
            # Level 4: Idempotency check
            if idempotency_key:
                await cur.execute(
                    "SELECT status_code, response_body, body_hash FROM idempotency_records WHERE key = %s",
                    (idempotency_key,),
                )
                cached = await cur.fetchone()
                if cached:
                    if cached["body_hash"] == current_body_hash:
                        response.status_code = cached["status_code"]
                        return json.loads(cached["response_body"])
                    else:
                        raise HTTPException(
                            status_code=422,
                            detail="Idempotency-Key reused with a different body",
                        )

            # Level 5: Rate Limiting (at most 5 attempts per email per minute)
            now_ms = int(time.time() * 1000)
            window_ms = 60 * 1000

            # Prune old attempts
            await cur.execute("DELETE FROM email_attempts WHERE timestamp < %s", (now_ms - 300000,))

            # Query attempts in sliding window
            await cur.execute(
                "SELECT timestamp FROM email_attempts WHERE email = %s AND timestamp >= %s ORDER BY timestamp ASC",
                (payload.email, now_ms - window_ms),
            )
            recent_attempts = await cur.fetchall()

            if len(recent_attempts) >= 5:
                oldest_timestamp = recent_attempts[0]["timestamp"]
                remaining_ms = oldest_timestamp + window_ms - now_ms
                retry_after = max(1, math.ceil(remaining_ms / 1000))
                await conn.commit()
                response.headers["Retry-After"] = str(retry_after)
                raise HTTPException(
                    status_code=429,
                    detail="Too many attempts for this email",
                    headers={"Retry-After": str(retry_after)},
                )

            # Record this attempt (failed attempts count too!)
            await cur.execute(
                "INSERT INTO email_attempts (email, timestamp) VALUES (%s, %s)",
                (payload.email, now_ms),
            )
            await conn.commit()

            # Level 2: Slot existence & Start time validation
            await cur.execute('SELECT id, start FROM slots WHERE id = %s FOR SHARE', (payload.slot_id,))
            slot = await cur.fetchone()
            if not slot:
                raise HTTPException(status_code=404, detail="The slot doesn't exist")

            now_utc = datetime.now(timezone.utc)
            slot_start = slot["start"]
            if slot_start.tzinfo is None:
                slot_start = slot_start.replace(tzinfo=timezone.utc)

            if slot_start <= now_utc:
                raise HTTPException(status_code=400, detail="The slot has already started")

            # Level 3: Concurrency check & insert
            await cur.execute(
                "SELECT id FROM bookings WHERE slot_id = %s AND status = 'confirmed'",
                (payload.slot_id,),
            )
            if await cur.fetchone():
                raise HTTPException(status_code=409, detail="Slot already booked")

            booking_id = "b_" + uuid.uuid4().hex[:14]
            created_at = datetime.now(timezone.utc)

            try:
                await cur.execute(
                    """
                    INSERT INTO bookings (id, slot_id, name, email, status, created_at)
                    VALUES (%s, %s, %s, %s, 'confirmed', %s)
                    RETURNING id, slot_id, name, email, status, created_at
                    """,
                    (booking_id, payload.slot_id, payload.name, payload.email, created_at),
                )
                booking_row = await cur.fetchone()
            except UniqueViolation:
                await conn.rollback()
                raise HTTPException(status_code=409, detail="Slot already booked")

            booking_obj = Booking(
                id=booking_row["id"],
                slot_id=booking_row["slot_id"],
                name=booking_row["name"],
                email=booking_row["email"],
                status=booking_row["status"],
                created_at=booking_row["created_at"],
            )

            # Save idempotency record if requested
            if idempotency_key:
                await cur.execute(
                    """
                    INSERT INTO idempotency_records (key, body_hash, status_code, response_body, created_at)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        idempotency_key,
                        current_body_hash,
                        201,
                        booking_obj.model_dump_json(),
                        created_at,
                    ),
                )

            await conn.commit()
            return booking_obj

@router.get("", response_model=PaginatedBookings)
async def list_person_bookings(
    email: str = Query(..., description="Email to list bookings for"),
    limit: int = Query(default=10, description="1 to 50. Anything else returns 400."),
    cursor: str | None = Query(default=None),
):
    if limit < 1 or limit > 50:
        raise HTTPException(status_code=400, detail="Invalid limit: must be between 1 and 50")

    normalized_email = email.strip().lower()

    async with get_connection() as conn:
        async with conn.cursor() as cur:
            query = """
                SELECT id, slot_id, name, email, status, created_at
                FROM bookings
                WHERE LOWER(email) = LOWER(%s)
            """
            params = [normalized_email]

            if cursor:
                try:
                    decoded = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
                    cursor_created = datetime.fromisoformat(decoded["c"])
                    cursor_id = decoded["id"]
                    query += " AND (created_at > %s OR (created_at = %s AND id > %s))"
                    params.extend([cursor_created, cursor_created, cursor_id])
                except Exception:
                    pass

            query += " ORDER BY created_at ASC, id ASC LIMIT %s"
            params.append(limit + 1)

            await cur.execute(query, params)
            rows = await cur.fetchall()

    next_cursor = None
    bookings_data = rows
    if len(rows) > limit:
        bookings_data = rows[:limit]
        last = bookings_data[-1]
        cursor_payload = {"c": last["created_at"].isoformat(), "id": last["id"]}
        next_cursor = base64.urlsafe_b64encode(json.dumps(cursor_payload).encode()).decode()

    bookings = [
        Booking(
            id=r["id"],
            slot_id=r["slot_id"],
            name=r["name"],
            email=r["email"],
            status=r["status"],
            created_at=r["created_at"],
        )
        for r in bookings_data
    ]

    return PaginatedBookings(bookings=bookings, next_cursor=next_cursor)

@router.get("/{id}", response_model=Booking)
async def get_booking(id: str):
    async with get_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT id, slot_id, name, email, status, created_at FROM bookings WHERE id = %s",
                (id,),
            )
            booking = await cur.fetchone()
            if not booking:
                raise HTTPException(status_code=404, detail="No booking with that id")

    return Booking(
        id=booking["id"],
        slot_id=booking["slot_id"],
        name=booking["name"],
        email=booking["email"],
        status=booking["status"],
        created_at=booking["created_at"],
    )

@router.delete("/{id}", response_model=Booking)
async def cancel_booking(id: str):
    async with get_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT id, slot_id, name, email, status, created_at FROM bookings WHERE id = %s FOR UPDATE",
                (id,),
            )
            booking = await cur.fetchone()
            if not booking:
                raise HTTPException(status_code=404, detail="No booking with that id")

            if booking["status"] == "cancelled":
                raise HTTPException(status_code=409, detail="Already cancelled")

            await cur.execute("UPDATE bookings SET status = 'cancelled' WHERE id = %s", (id,))
            await conn.commit()

    return Booking(
        id=booking["id"],
        slot_id=booking["slot_id"],
        name=booking["name"],
        email=booking["email"],
        status="cancelled",
        created_at=booking["created_at"],
    )
