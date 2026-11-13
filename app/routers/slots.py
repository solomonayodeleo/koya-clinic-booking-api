from fastapi import APIRouter, Query, Security
from app.auth import APIKeyRoute, api_key_header
from app.database import get_connection
from app.models import ErrorResponse, SlotWithAvailability

router = APIRouter(
    prefix="/slots",
    tags=["Slots"],
    route_class=APIKeyRoute,
    dependencies=[Security(api_key_header)],
    responses={
        401: {"model": ErrorResponse, "description": "Missing or invalid X-API-Key"},
        "default": {"model": ErrorResponse, "description": "Request failed"},
    },
)

@router.get(
    "",
    response_model=dict[str, list[SlotWithAvailability]],
    summary="List slots",
    response_description="Slots with their current availability",
    description=(
        "Returns slots ordered by start time, earliest first. "
        "A slot with a confirmed booking has `available: false`."
    ),
)
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
