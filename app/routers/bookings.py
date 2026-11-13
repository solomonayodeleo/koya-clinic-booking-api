import base64
from datetime import datetime, timezone
import json
import math
import time
import uuid
from fastapi import APIRouter, Body, Header, HTTPException, Query, status
from fastapi.responses import JSONResponse
from pydantic import EmailStr, TypeAdapter, ValidationError
from psycopg.errors import UniqueViolation
from app.auth import APIKeyRoute
from app.database import get_connection
from app.models import Booking, NewBooking, PaginatedBookings

router = APIRouter(prefix="/bookings", tags=["Bookings"], route_class=APIKeyRoute)

email_adapter = TypeAdapter(EmailStr)


async def record_attempt(cur, email: str) -> None:
    await cur.execute("SELECT pg_advisory_xact_lock(2, hashtext(%s))", (email,))
    now_ms = int(time.time() * 1000)
    window_ms = 60_000
    await cur.execute(
        "DELETE FROM email_attempts WHERE email = %s AND timestamp <= %s",
        (email, now_ms - window_ms),
    )
    await cur.execute(
        "SELECT count(*) AS count, min(timestamp) AS oldest FROM email_attempts WHERE email = %s",
        (email,),
    )
    attempts = await cur.fetchone()
    if attempts["count"] >= 5:
        retry_after = math.ceil((attempts["oldest"] + window_ms - now_ms) / 1000)
        raise HTTPException(
            status_code=429,
            detail="Too many attempts for this email",
            headers={"Retry-After": str(retry_after)},
        )
    await cur.execute(
        "INSERT INTO email_attempts (email, timestamp) VALUES (%s, %s)",
        (email, now_ms),
    )


async def insert_booking(cur, payload: NewBooking) -> Booking:
    await cur.execute("SELECT start FROM slots WHERE id = %s", (payload.slot_id,))
    slot = await cur.fetchone()
    if not slot:
        raise HTTPException(status_code=404, detail="The slot doesn't exist")
    if slot["start"] <= datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="The slot has already started")

    await cur.execute(
        """
        INSERT INTO bookings (id, slot_id, name, email, status, created_at)
        VALUES (%s, %s, %s, %s, 'confirmed', %s)
        RETURNING id, slot_id, name, email, status, created_at
        """,
        ("b_" + uuid.uuid4().hex, payload.slot_id, payload.name,
         payload.email, datetime.now(timezone.utc)),
    )
    return Booking.model_validate(await cur.fetchone())


@router.post("", status_code=status.HTTP_201_CREATED, response_model=Booking)
async def create_booking(
    body: dict = Body(),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    body_hash = json.dumps(body, sort_keys=True)
    async with get_connection() as conn, conn.cursor() as cur:
        # Reset takes this same lock exclusively before replacing the data.
        await cur.execute("SELECT pg_advisory_xact_lock_shared(0, 1)")
        if idempotency_key is not None:
            await cur.execute("SELECT pg_advisory_xact_lock(1, hashtext(%s))", (idempotency_key,))
            await cur.execute(
                "SELECT status_code, response_body, body_hash FROM idempotency_records WHERE key = %s",
                (idempotency_key,),
            )
            cached = await cur.fetchone()
            if cached:
                if cached["body_hash"] != body_hash:
                    raise HTTPException(status_code=422, detail="Idempotency-Key reused with a different body")
                return JSONResponse(json.loads(cached["response_body"]), status_code=cached["status_code"])

        # A valid email identifies the rate-limit bucket even when another field is invalid.
        try:
            raw_email = body.get("email")
            email = email_adapter.validate_python(raw_email.strip().lower() if isinstance(raw_email, str) else raw_email)
        except ValidationError:
            raise HTTPException(status_code=400, detail="A valid email is required")
        await record_attempt(cur, email)

        # Roll back a conflicting insert without losing the attempt or its cached response.
        try:
            async with conn.transaction():
                payload = NewBooking.model_validate(body)
                booking = await insert_booking(cur, payload)
            response_code, response_body = 201, booking.model_dump(mode="json")
        except ValidationError as exc:
            field = exc.errors()[0]["loc"][0]
            response_code, response_body = 400, {"error": f"Invalid {field}"}
        except HTTPException as exc:
            response_code, response_body = exc.status_code, {"error": exc.detail}
        except UniqueViolation:
            response_code, response_body = 409, {"error": "Slot already booked"}

        if idempotency_key is not None:
            await cur.execute(
                """
                INSERT INTO idempotency_records (key, body_hash, status_code, response_body, created_at)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (idempotency_key, body_hash, response_code, json.dumps(response_body), datetime.now(timezone.utc)),
            )
        return JSONResponse(response_body, status_code=response_code)

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

            if cursor is not None:
                try:
                    decoded = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
                    cursor_created = datetime.fromisoformat(decoded["c"])
                    cursor_id = decoded["id"]
                    if not isinstance(cursor_id, str) or cursor_created.tzinfo is None:
                        raise ValueError("Invalid cursor values")
                    query += " AND (created_at > %s OR (created_at = %s AND id > %s))"
                    params.extend([cursor_created, cursor_created, cursor_id])
                except (ValueError, KeyError, TypeError):
                    raise HTTPException(status_code=400, detail="Invalid cursor")

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
