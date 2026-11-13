import pytest
from httpx import ASGITransport, AsyncClient

from app.config import API_KEY
from app.main import app


@pytest.mark.parametrize("path", ["/bookings", "/reset"])
@pytest.mark.parametrize(
    ("key", "expected_status"),
    [(None, 401), ("wrong-" + API_KEY, 401), (API_KEY, 400)],
    ids=["missing-key", "wrong-key", "valid-key"],
)
async def test_authentication_precedes_json_parsing(path, key, expected_status):
    headers = {"Content-Type": "application/json"}
    if key is not None:
        headers["X-API-Key"] = key

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(path, content="{", headers=headers)

    assert response.status_code == expected_status
    assert set(response.json()) == {"error"}
