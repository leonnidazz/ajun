import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.config import is_admin_email
from tests.conftest import create_test_id_token


@pytest.mark.asyncio
async def test_register_user_by_google_sub_only(async_client: AsyncClient, db_session: AsyncSession):
    """Verifies user creation by google_sub and campus_domain_match flag (without setting is_identity_verified in Phase 1a)."""
    token = create_test_id_token(
        sub="sub-new-001",
        email="budi@ui.ac.id",
        name="Budi UI",
    )
    res = await async_client.post("/api/v1/auth/google-login", json={"id_token": token})
    assert res.status_code == 200
    data = res.json()

    assert data["token_type"] == "bearer"
    assert "access_token" in data
    assert "refresh_token" in data
    
    user_res = data["user"]
    assert user_res["email"] == "budi@ui.ac.id"
    assert user_res["full_name"] == "Budi UI"
    assert user_res["campus_domain_match"] is True

    # Database check: Phase 1a MUST NOT set is_identity_verified or campus_verified_at
    stmt = select(User).where(User.google_sub == "sub-new-001")
    db_user = (await db_session.execute(stmt)).scalar_one()
    assert db_user.google_sub == "sub-new-001"
    assert db_user.email == "budi@ui.ac.id"
    assert db_user.is_identity_verified is False
    assert db_user.campus_verified_at is None


@pytest.mark.asyncio
async def test_same_sub_refreshes_email_and_name(async_client: AsyncClient, db_session: AsyncSession):
    """Verifies that subsequent login with the same google_sub updates changed email and name."""
    tok1 = create_test_id_token(sub="sub-refresh-002", email="old@ui.ac.id", name="Old Name")
    res1 = await async_client.post("/api/v1/auth/google-login", json={"id_token": tok1})
    assert res1.status_code == 200
    uid1 = res1.json()["user"]["id"]

    # Same sub, updated email and name
    tok2 = create_test_id_token(sub="sub-refresh-002", email="updated@ui.ac.id", name="New Name")
    res2 = await async_client.post("/api/v1/auth/google-login", json={"id_token": tok2})
    assert res2.status_code == 200
    uid2 = res2.json()["user"]["id"]

    assert uid1 == uid2
    assert res2.json()["user"]["email"] == "updated@ui.ac.id"
    assert res2.json()["user"]["full_name"] == "New Name"


@pytest.mark.asyncio
async def test_reject_email_conflict_different_google_sub(async_client: AsyncClient):
    """Verifies that an attempt to register with an existing email under a different google_sub is rejected safely."""
    tok1 = create_test_id_token(sub="sub-user-original", email="exclusive@ui.ac.id")
    res1 = await async_client.post("/api/v1/auth/google-login", json={"id_token": tok1})
    assert res1.status_code == 200

    # Different google_sub claiming the same email
    tok2 = create_test_id_token(sub="sub-user-imposter", email="exclusive@ui.ac.id")
    res2 = await async_client.post("/api/v1/auth/google-login", json={"id_token": tok2})
    assert res2.status_code == 409
    assert "already associated" in res2.json()["detail"].lower()


@pytest.mark.asyncio
async def test_is_admin_email_helper():
    assert is_admin_email("admin@ui.ac.id") is True
    assert is_admin_email("superadmin@ugm.ac.id") is True
    assert is_admin_email("regular@ui.ac.id") is False
    assert is_admin_email(None) is False


@pytest.mark.asyncio
async def test_request_body_size_limit(async_client: AsyncClient):
    """Verifies that payloads exceeding 1 MB are rejected with HTTP 413."""
    oversized_token = "a" * (1024 * 1024 + 100)
    res = await async_client.post(
        "/api/v1/auth/google-login",
        content=oversized_token.encode("utf-8"),
        headers={"Content-Length": str(len(oversized_token)), "Content-Type": "application/json"},
    )
    assert res.status_code == 413
