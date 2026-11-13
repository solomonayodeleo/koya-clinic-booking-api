from fastapi import APIRouter, Query
from app.auth import APIKeyRoute
from app.database import get_connection
from app.models import SlotWithAvailability

router = APIRouter(prefix="/slots", tags=["Slots"], route_class=APIKeyRoute)

@router.get("", response_model=dict[str, list[SlotWithAvailability]])
async def list_slots(provider: str | None = Query(default=None, description="Only this provider's slots (exact match)")):
    async with get_connection() as conn:
        async with conn.cursor() as cur:
            query = """
                SELECT s.id, s.provider, s.start, s."end",
                       CASE WHEN b.id IS NOT NULL THEN false ELSE true END AS available
                FROM slots s
                LEFT JOIN bookings b ON b.slot_id = s.id AND b.status = 'confirmed'
            """
            params = []
            if provider is not None:
                query += " WHERE s.provider = %s"
                params.append(provider)

            query += ' ORDER BY s.start ASC, s.id ASC;'
            await cur.execute(query, params)
            rows = await cur.fetchall()

    slots = [
        SlotWithAvailability(
            id=r["id"],
            provider=r["provider"],
            start=r["start"],
            end=r["end"],
            available=r["available"],
        )
        for r in rows
    ]
    return {"slots": slots}
