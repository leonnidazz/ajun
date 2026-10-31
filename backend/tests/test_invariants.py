import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.configuration import SystemConfiguration
from app.main import check_startup_invariants


from tests.conftest import TestingSessionLocal


@pytest.mark.asyncio
async def test_health_check_endpoint(async_client: AsyncClient):
    """Verifies that GET /health is accessible without any prefix."""
    res = await async_client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["app"] == "Ajun"
    assert data["phase"] == "Phase 1a"


@pytest.mark.asyncio
async def test_startup_invariant_check_success(db_session: AsyncSession):
    """Verifies that valid configuration passes startup invariant check."""
    await check_startup_invariants(session_factory=TestingSessionLocal)


@pytest.mark.asyncio
async def test_startup_invariant_fails_on_violation(db_session: AsyncSession):
    """Verifies that REOPEN_MIN_LEAD_MINUTES < MIN_CONFIRMATION_LEAD_MINUTES raises RuntimeError (no silent clamping)."""
    # Temporarily violate invariant
    await db_session.execute(
        update(SystemConfiguration)
        .where(SystemConfiguration.key == "REOPEN_MIN_LEAD_MINUTES")
        .values(value="10")  # 10 < 15
    )
    await db_session.commit()

    with pytest.raises(RuntimeError) as exc_info:
        await check_startup_invariants(session_factory=TestingSessionLocal)
    
    assert "Startup invariant check failed" in str(exc_info.value)
    assert "REOPEN_MIN_LEAD_MINUTES (10) < MIN_CONFIRMATION_LEAD_MINUTES (15)" in str(exc_info.value)

    # Restore correct configuration
    await db_session.execute(
        update(SystemConfiguration)
        .where(SystemConfiguration.key == "REOPEN_MIN_LEAD_MINUTES")
        .values(value="30")
    )
    await db_session.commit()
