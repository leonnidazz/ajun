import pytest
from httpx import AsyncClient
from tests.conftest import create_test_id_token


@pytest.mark.asyncio
async def test_auth_rate_limiting_google_login(async_client: AsyncClient):
    tok = create_test_id_token(sub="sub-ratelimit-login", email="rate@ui.ac.id")

    # 10 allowed requests (limit is 10/min)
    for _ in range(10):
        res = await async_client.post("/api/v1/auth/google-login", json={"id_token": tok})
        assert res.status_code == 200

    # 11th request triggers HTTP 429 Too Many Requests
    blocked = await async_client.post("/api/v1/auth/google-login", json={"id_token": tok})
    assert blocked.status_code == 429
    assert "rate limit exceeded" in blocked.json()["detail"].lower()
    assert "retry-after" in blocked.headers


@pytest.mark.asyncio
async def test_auth_rate_limiting_refresh(async_client: AsyncClient):
    # Test refresh rate limit with bad token (counts against rate limiter)
    for _ in range(10):
        res = await async_client.post("/api/v1/auth/refresh", json={"refresh_token": "some-random-token"})
        assert res.status_code == 401

    blocked = await async_client.post("/api/v1/auth/refresh", json={"refresh_token": "some-random-token"})
    assert blocked.status_code == 429
    assert "retry-after" in blocked.headers
