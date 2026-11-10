import asyncio
from datetime import datetime, timedelta, timezone
import pytest
from httpx import ASGITransport, AsyncClient
from app.config import API_KEY
from app.main import app

HEADERS = {"X-API-Key": API_KEY}

@pytest.fixture(autouse=True)
async def setup_db():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Reset with standard test slots
        now = datetime.now(timezone.utc)
        slots = [
            {
                "id": "s1",
                "provider": "Dr Ade",
                "start": (now + timedelta(days=1)).isoformat(),
                "end": (now + timedelta(days=1, hours=1)).isoformat(),
            },
            {
                "id": "s2",
                "provider": "Dr Ade",
                "start": (now + timedelta(days=2)).isoformat(),
                "end": (now + timedelta(days=2, hours=1)).isoformat(),
            },
            {
                "id": "s3",
                "provider": "Dr Fatima",
                "start": (now + timedelta(days=3)).isoformat(),
                "end": (now + timedelta(days=3, hours=1)).isoformat(),
            },
            {
                "id": "s_past",
                "provider": "Dr Past",
                "start": (now - timedelta(days=1)).isoformat(),
                "end": (now - timedelta(days=1) + timedelta(hours=1)).isoformat(),
            },
        ]
        res = await client.post("/reset", json={"slots": slots}, headers=HEADERS)
        assert res.status_code == 200

# Level 1 Tests
@pytest.mark.asyncio
async def test_level_1_core_flow():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. List slots
        res = await client.get("/slots", headers=HEADERS)
        assert res.status_code == 200
        slots = res.json()["slots"]
        assert len(slots) >= 3
        # Should be ordered earliest start first
        starts = [s["start"] for s in slots]
        assert starts == sorted(starts)

        # Provider filter
        res_filtered = await client.get("/slots?provider=Dr%20Ade", headers=HEADERS)
        assert res_filtered.status_code == 200
        assert all(s["provider"] == "Dr Ade" for s in res_filtered.json()["slots"])

        # 2. Book a slot
        book_res = await client.post(
            "/bookings",
            json={"slot_id": "s1", "name": "Ada Obi", "email": "ada@example.com"},
            headers=HEADERS,
        )
        assert book_res.status_code == 201
        booking = book_res.json()
        assert booking["slot_id"] == "s1"
        assert booking["name"] == "Ada Obi"
        assert booking["email"] == "ada@example.com"
        assert booking["status"] == "confirmed"
        assert "id" in booking
        booking_id = booking["id"]

        # 3. Look up booking by id
        lookup_res = await client.get(f"/bookings/{booking_id}", headers=HEADERS)
        assert lookup_res.status_code == 200
        assert lookup_res.json()["id"] == booking_id

        # 4. Check slot availability reflects the booking
        slots_after = (await client.get("/slots", headers=HEADERS)).json()["slots"]
        s1 = next(s for s in slots_after if s["id"] == "s1")
        assert s1["available"] is False

# Level 2 Tests: Auth & Validation
@pytest.mark.asyncio
async def test_level_2_auth_and_validation():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Missing API Key -> 401
        res = await client.get("/slots")
        assert res.status_code == 401
        assert "error" in res.json()

        # Wrong API Key -> 401
        res = await client.get("/slots", headers={"X-API-Key": "wrong-key"})
        assert res.status_code == 401

        # Missing fields -> 400
        res = await client.post("/bookings", json={"slot_id": "", "name": "Ada", "email": "a@b.com"}, headers=HEADERS)
        assert res.status_code == 400

        # Invalid email -> 400
        res = await client.post("/bookings", json={"slot_id": "s2", "name": "Ada", "email": "invalid-email"}, headers=HEADERS)
        assert res.status_code == 400

        # Slot doesn't exist -> 404
        res = await client.post("/bookings", json={"slot_id": "nonexistent_999", "name": "Ada", "email": "ada2@example.com"}, headers=HEADERS)
        assert res.status_code == 404
        assert "error" in res.json()

        # Slot in the past -> 400
        res = await client.post("/bookings", json={"slot_id": "s_past", "name": "Ada", "email": "ada3@example.com"}, headers=HEADERS)
        assert res.status_code == 400
        assert "started" in res.json()["error"].lower()

        # Trim spaces & lowercased email
        res = await client.post(
            "/bookings",
            json={"slot_id": "s2", "name": "  Chinwe Eze  ", "email": "  CHINWE@Example.COM  "},
            headers=HEADERS,
        )
        assert res.status_code == 201
        b = res.json()
        assert b["name"] == "Chinwe Eze"
        assert b["email"] == "chinwe@example.com"

# Level 3 Tests: Concurrency & Cancellation
@pytest.mark.asyncio
async def test_level_3_concurrency_and_cancellation():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Two simultaneous requests booking the same slot 's3'
        async def try_book(name: str, email: str):
            return await client.post(
                "/bookings",
                json={"slot_id": "s3", "name": name, "email": email},
                headers=HEADERS,
            )

        res1, res2 = await asyncio.gather(
            try_book("Patient One", "patient1@example.com"),
            try_book("Patient Two", "patient2@example.com"),
        )

        status_codes = {res1.status_code, res2.status_code}
        assert status_codes == {201, 409}, f"Expected {201, 409}, got {status_codes}"

        success_res = res1 if res1.status_code == 201 else res2
        booking_id = success_res.json()["id"]

        # Cancel the booking
        cancel_res = await client.delete(f"/bookings/{booking_id}", headers=HEADERS)
        assert cancel_res.status_code == 200
        assert cancel_res.json()["status"] == "cancelled"

        # Slot should be available again!
        slots = (await client.get("/slots", headers=HEADERS)).json()["slots"]
        s3 = next(s for s in slots if s["id"] == "s3")
        assert s3["available"] is True

        # Second cancellation -> 409
        second_cancel = await client.delete(f"/bookings/{booking_id}", headers=HEADERS)
        assert second_cancel.status_code == 409
        assert "error" in second_cancel.json()

# Level 4 Tests: Idempotency & Cursor Pagination
@pytest.mark.asyncio
async def test_level_4_idempotency_and_pagination():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Idempotency: exact replay
        payload = {"slot_id": "s3", "name": "Idem Patient", "email": "idem@example.com"}
        headers_idem = {**HEADERS, "Idempotency-Key": "key-unique-12345"}

        res_first = await client.post("/bookings", json=payload, headers=headers_idem)
        assert res_first.status_code == 201
        first_id = res_first.json()["id"]

        # Exact retry with same key & body
        res_second = await client.post("/bookings", json=payload, headers=headers_idem)
        assert res_second.status_code == 201
        assert res_second.json()["id"] == first_id

        # Reusing key with different body -> 422
        payload_diff = {"slot_id": "s3", "name": "Different Name", "email": "idem@example.com"}
        res_conflict = await client.post("/bookings", json=payload_diff, headers=headers_idem)
        assert res_conflict.status_code == 422
        assert "error" in res_conflict.json()

        # Cursor Pagination: list person's bookings
        # Create multiple slots and bookings for the same user
        now = datetime.now(timezone.utc)
        more_slots = [
            {"id": f"page_s_{i}", "provider": "Dr Ade", "start": (now + timedelta(days=10 + i)).isoformat(), "end": (now + timedelta(days=10 + i, hours=1)).isoformat()}
            for i in range(5)
        ]
        await client.post("/reset", json={"slots": more_slots}, headers=HEADERS)

        for s in more_slots:
            await client.post(
                "/bookings",
                json={"slot_id": s["id"], "name": "Page User", "email": "page@example.com"},
                headers=HEADERS,
            )

        # Page 1 (limit 2)
        p1 = await client.get("/bookings?email=PAGE@EXAMPLE.COM&limit=2", headers=HEADERS)
        assert p1.status_code == 200
        p1_data = p1.json()
        assert len(p1_data["bookings"]) == 2
        assert p1_data["next_cursor"] is not None

        # Page 2 using cursor
        p2 = await client.get(f"/bookings?email=page@example.com&limit=2&cursor={p1_data['next_cursor']}", headers=HEADERS)
        assert p2.status_code == 200
        p2_data = p2.json()
        assert len(p2_data["bookings"]) == 2
        assert p2_data["next_cursor"] is not None

        # Invalid limit -> 400
        bad_limit = await client.get("/bookings?email=page@example.com&limit=0", headers=HEADERS)
        assert bad_limit.status_code == 400
        bad_limit_high = await client.get("/bookings?email=page@example.com&limit=51", headers=HEADERS)
        assert bad_limit_high.status_code == 400

# Level 5 Tests: Rate Limiting
@pytest.mark.asyncio
async def test_level_5_rate_limiting():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create 10 slots
        now = datetime.now(timezone.utc)
        slots = [
            {"id": f"rl_{i}", "provider": "Dr RL", "start": (now + timedelta(days=20 + i)).isoformat(), "end": (now + timedelta(days=20 + i, hours=1)).isoformat()}
            for i in range(10)
        ]
        await client.post("/reset", json={"slots": slots}, headers=HEADERS)

        spam_email = "spammer@example.com"
        # First 5 attempts should succeed
        for i in range(5):
            res = await client.post(
                "/bookings",
                json={"slot_id": f"rl_{i}", "name": "Spam User", "email": spam_email},
                headers=HEADERS,
            )
            assert res.status_code == 201

        # 6th attempt must be rejected with 429 and Retry-After header
        res_6 = await client.post(
            "/bookings",
            json={"slot_id": "rl_5", "name": "Spam User", "email": spam_email},
            headers=HEADERS,
        )
        assert res_6.status_code == 429
        assert "error" in res_6.json()
        assert "Retry-After" in res_6.headers
        retry_val = int(res_6.headers["Retry-After"])
        assert 1 <= retry_val <= 60

        # Different email is NOT blocked
        res_other = await client.post(
            "/bookings",
            json={"slot_id": "rl_5", "name": "Good User", "email": "good@example.com"},
            headers=HEADERS,
        )
        assert res_other.status_code == 201
