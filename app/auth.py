from hmac import compare_digest

from fastapi import HTTPException, Request
from fastapi.routing import APIRoute

from app.config import API_KEY


class APIKeyRoute(APIRoute):
    def get_route_handler(self):
        handle_request = super().get_route_handler()

        async def require_api_key(request: Request):
            key = request.headers.get("X-API-Key")
            if not key or not compare_digest(key.encode(), API_KEY.encode()):
                raise HTTPException(
                    status_code=401,
                    detail="Unauthorized: missing or invalid X-API-Key header",
                )
            return await handle_request(request)

        return require_api_key
