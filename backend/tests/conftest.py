import os
import sys
import json
import base64
import time
import pytest
import pytest_asyncio
from unittest.mock import patch
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes, serialization

# Add backend directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Load settings and verify Postgres test database guard
from app.config import settings

# --- DATABASE GUARD CHECK (MANDATORY REQUIREMENT B) ---
DATABASE_URL_PROD = settings.DATABASE_URL
DATABASE_URL_TEST = settings.DATABASE_URL_TEST

if not DATABASE_URL_TEST:
    raise RuntimeError("CRITICAL: DATABASE_URL_TEST is missing. Tests must run against a dedicated PostgreSQL database.")

if DATABASE_URL_TEST == DATABASE_URL_PROD:
    raise RuntimeError(
        f"CRITICAL SAFETY VIOLATION: DATABASE_URL_TEST ({DATABASE_URL_TEST}) equals DATABASE_URL. "
        "Test execution refused to protect production/development data."
    )

if not DATABASE_URL_TEST.startswith("postgresql"):
    raise RuntimeError(f"CRITICAL: DATABASE_URL_TEST must be a PostgreSQL connection string (got: {DATABASE_URL_TEST}).")

# Generate test RSA key pair for cryptographic token signing (Requirement C)
TEST_KID = "ajun-test-key-2026"
_TEST_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
TEST_PUBLIC_KEY_PEM = _TEST_PRIVATE_KEY.public_key().public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo,
).decode("utf-8")

from sqlalchemy.pool import NullPool

# Create test PostgreSQL async engine with NullPool
test_engine = create_async_engine(
    DATABASE_URL_TEST,
    echo=False,
    future=True,
    poolclass=NullPool,
)

TestingSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

from app.database import get_db
from app.main import app
from app.utils.rate_limiter import auth_rate_limiter, logout_rate_limiter


async def override_get_db():
    async with TestingSessionLocal() as session:
        yield session


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def patch_google_certs_fetch():
    """Patches Google's certificate fetcher so google-auth verifies real RSA signatures with our test key."""
    with patch("google.oauth2.id_token._fetch_certs", return_value={TEST_KID: TEST_PUBLIC_KEY_PEM}):
        yield


@pytest_asyncio.fixture(autouse=True)
async def cleanup_test_database():
    """Cleans up data in PostgreSQL before each test to guarantee test isolation."""
    auth_rate_limiter.reset()
    logout_rate_limiter.reset()

    async with test_engine.begin() as conn:
        # Truncate users and refresh_tokens, preserving schema and system_configurations
        await conn.execute(text("TRUNCATE TABLE refresh_tokens, users CASCADE;"))
    yield
    async with test_engine.begin() as conn:
        await conn.execute(text("TRUNCATE TABLE refresh_tokens, users CASCADE;"))


@pytest_asyncio.fixture
async def async_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture
async def db_session():
    async with TestingSessionLocal() as session:
        yield session


def _b64_url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def create_test_id_token(
    sub: str = "sub-1234567890",
    email: str = "mahasiswa@ui.ac.id",
    name: str = "Mahasiswa Ajun",
    email_verified: bool = True,
    aud: str = "mock-client-id-web",
    iss: str = "https://accounts.google.com",
    exp_offset_seconds: int = 3600,
    alg: str = "RS256",
    kid: str = TEST_KID,
    forge_signature: bool = False,
    custom_signature: str = None,
) -> str:
    """Creates a real RSA-signed Google ID Token using our local test RSA key."""
    now_ts = int(time.time())
    exp_ts = now_ts + exp_offset_seconds

    header = {"alg": alg, "typ": "JWT"}
    if kid:
        header["kid"] = kid

    payload = {
        "iss": iss,
        "sub": sub,
        "email": email,
        "email_verified": email_verified,
        "name": name,
        "aud": aud,
        "exp": exp_ts,
        "iat": now_ts,
    }

    # Handle omitted fields if needed
    if sub is None:
        payload.pop("sub")
    if email is None:
        payload.pop("email")

    h_b64 = _b64_url_encode(json.dumps(header).encode("utf-8"))
    p_b64 = _b64_url_encode(json.dumps(payload).encode("utf-8"))
    signing_input = f"{h_b64}.{p_b64}".encode("utf-8")

    if alg == "none":
        return f"{h_b64}.{p_b64}."

    if custom_signature is not None:
        return f"{h_b64}.{p_b64}.{custom_signature}"

    if alg == "RS256":
        sig = _TEST_PRIVATE_KEY.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
        if forge_signature:
            # Corrupt the signature bytes
            sig = bytearray(sig)
            sig[0] ^= 0xFF
            sig = bytes(sig)
        sig_b64 = _b64_url_encode(sig)
        return f"{h_b64}.{p_b64}.{sig_b64}"

    return f"{h_b64}.{p_b64}."
