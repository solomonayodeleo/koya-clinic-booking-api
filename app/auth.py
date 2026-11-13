from hmac import compare_digest

from fastapi import HTTPException, Request
from fastapi.routing import APIRoute
from fastapi.security import APIKeyHeader

from app.config import API_KEY


api_key_header = APIKeyHeader(
    name="X-API-Key",
    scheme_name="apiKey",
    description="Enter the configured API key to authorize requests.",
    auto_error=False,
)


class APIKeyRoute(APIRoute):
    """Authenticate before FastAPI reads or validates the request body."""

    def get_route_handler(self):
        handle_request = super().get_route_handler()

        async def require_api_key(request: Request):
            key = await api_key_header(request)
            if not key or not compare_digest(key.encode(), API_KEY.encode()):
                raise HTTPException(
                    status_code=401,
                    detail="Unauthorized: missing or invalid X-API-Key header",
                )
            return await handle_request(request)

        return require_api_key
