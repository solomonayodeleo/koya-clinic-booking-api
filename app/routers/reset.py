from fastapi import APIRouter, Security
from app.auth import APIKeyRoute, api_key_header
from app.database import get_connection
from app.models import ErrorResponse, ResetRequest

router = APIRouter(
    prefix="/reset",
    tags=["Reset"],
    route_class=APIKeyRoute,
    dependencies=[Security(api_key_header)],
    responses={
        401: {"model": ErrorResponse, "description": "Missing or invalid X-API-Key"},
        "default": {"model": ErrorResponse, "description": "Request failed"},
    },
)

@router.post(
    "",
    status_code=200,
    summary="Replace all slots",
    response_description="Slots replaced",
    description=(
        "Replaces all slots with the supplied list, which may include past slots. "
        "This clears existing bookings, saved retry responses, and rate-limit attempts."
    ),
    responses={
        400: {"model": ErrorResponse, "description": "Invalid slot payload"},
    },
)
async def reset_slots(payload: ResetRequest):
    async with get_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT pg_advisory_xact_lock(0, 1)")
            await cur.execute("DELETE FROM bookings;")
            await cur.execute("DELETE FROM slots;")
            await cur.execute("DELETE FROM idempotency_records;")
            await cur.execute("DELETE FROM email_attempts;")

            for slot in payload.slots:
                await cur.execute(
                    """
                    INSERT INTO slots (id, provider, start, "end")
                    VALUES (%s, %s, %s, %s)
                    """,
                    (slot.id, slot.provider, slot.start, slot.end),
                )
        await conn.commit()

    return {"status": "ok"}
