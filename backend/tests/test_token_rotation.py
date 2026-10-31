import asyncio
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.token import RefreshToken
from tests.conftest import create_test_id_token


@pytest.mark.asyncio
async def test_normal_atomic_refresh_rotation(async_client: AsyncClient, db_session: AsyncSession):
    tok = create_test_id_token(sub="sub-rot-single", email="rot@ui.ac.id")
    login_res = await async_client.post("/api/v1/auth/google-login", json={"id_token": tok})
    assert login_res.status_code == 200
    token_1 = login_res.json()["refresh_token"]

    # Rotate token_1 -> token_2
    res_rot = await async_client.post("/api/v1/auth/refresh", json={"refresh_token": token_1})
    assert res_rot.status_code == 200
    token_2 = res_rot.json()["refresh_token"]
    assert token_2 != token_1

    # Verify database state
    stmt = select(RefreshToken)
    tokens = (await db_session.execute(stmt)).scalars().all()
    assert len(tokens) == 2
    used_tokens = [t for t in tokens if t.used_at is not None]
    assert len(used_tokens) == 1


@pytest.mark.asyncio
async def test_concurrent_double_refresh_race_safe(async_client: AsyncClient):
    """CRITICAL CONCURRENCY TEST (Requirement D):
    Two simultaneous refresh requests executed against PostgreSQL with the exact same token.
    Exactly one request must succeed with 200 OK, while the other must be rejected with 401.
    """
    tok = create_test_id_token(sub="sub-concurrency-test", email="concurrent@ui.ac.id")
    login_res = await async_client.post("/api/v1/auth/google-login", json={"id_token": tok})
    assert login_res.status_code == 200
    initial_refresh_token = login_res.json()["refresh_token"]

    # Launch two simultaneous refresh requests
    req1 = async_client.post("/api/v1/auth/refresh", json={"refresh_token": initial_refresh_token})
    req2 = async_client.post("/api/v1/auth/refresh", json={"refresh_token": initial_refresh_token})

    res1, res2 = await asyncio.gather(req1, req2)

    status_codes = sorted([res1.status_code, res2.status_code])
    # Exactly one must succeed (200) and one must fail (401)
    assert status_codes == [200, 401], f"Expected exactly one 200 and one 401, got {status_codes}"


@pytest.mark.asyncio
async def test_token_reuse_revokes_entire_family(async_client: AsyncClient):
    """CRITICAL SECURITY TEST:
    1. Login -> Token A.
    2. Rotation: Token A -> Token B.
    3. Attacker replays Token A. Backend detects reuse and revokes entire family.
    4. Legitimate user using Token B is now rejected because family was revoked.
    """
    tok = create_test_id_token(sub="sub-reuse-detection", email="reuse@ui.ac.id")
    login_res = await async_client.post("/api/v1/auth/google-login", json={"id_token": tok})
    token_a = login_res.json()["refresh_token"]

    # Legitimate rotation -> Token B
    res_b = await async_client.post("/api/v1/auth/refresh", json={"refresh_token": token_a})
    assert res_b.status_code == 200
    token_b = res_b.json()["refresh_token"]

    # Attacker replays Token A!
    replay_res = await async_client.post("/api/v1/auth/refresh", json={"refresh_token": token_a})
    assert replay_res.status_code == 401

    # Legitimate user tries to use Token B
    subsequent_res = await async_client.post("/api/v1/auth/refresh", json={"refresh_token": token_b})
    assert subsequent_res.status_code == 401


@pytest.mark.asyncio
async def test_logout_revokes_whole_family(async_client: AsyncClient):
    """Verifies that calling logout revokes the caller's whole refresh-token family."""
    tok = create_test_id_token(sub="sub-logout-family", email="logout@ui.ac.id")
    login_res = await async_client.post("/api/v1/auth/google-login", json={"id_token": tok})
    token_1 = login_res.json()["refresh_token"]

    # Rotate once -> token_2
    rot_res = await async_client.post("/api/v1/auth/refresh", json={"refresh_token": token_1})
    assert rot_res.status_code == 200
    token_2 = rot_res.json()["refresh_token"]

    # Logout with token_2
    logout_res = await async_client.post("/api/v1/auth/logout", json={"refresh_token": token_2})
    assert logout_res.status_code == 200

    # Attempt to refresh with token_2 or token_1 must be rejected
    fail_res = await async_client.post("/api/v1/auth/refresh", json={"refresh_token": token_2})
    assert fail_res.status_code == 401
