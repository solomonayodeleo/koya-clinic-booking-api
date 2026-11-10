from fastapi import Header, HTTPException
from app.config import API_KEY

async def verify_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    if not x_api_key or x_api_key != API_KEY:
        raise HTTPException(
            status_code=401,
            detail="Unauthorized: missing or invalid X-API-Key header"
        )
    return x_api_key
