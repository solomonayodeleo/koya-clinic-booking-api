from fastapi import APIRouter, Depends
from app.auth import verify_api_key
from app.database import get_connection
from app.models import ResetRequest

router = APIRouter(prefix="/reset", tags=["Reset"], dependencies=[Depends(verify_api_key)])

@router.post("", status_code=200)
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
