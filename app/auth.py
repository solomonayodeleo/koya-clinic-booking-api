from hmac import compare_digest

from fastapi import Header, HTTPException
from app.config import API_KEY

async def verify_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    if not x_api_key or not compare_digest(x_api_key.encode(), API_KEY.encode()):
        raise HTTPException(
            status_code=401,
            detail="Unauthorized: missing or invalid X-API-Key header"
        )
    return x_api_key
