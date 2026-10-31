import uuid
import secrets
import hashlib
import hmac
import base64
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Tuple

from sqlalchemy import select, update, text
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from app.config import settings
from app.models.user import User
from app.models.token import RefreshToken
from app.models.configuration import SystemConfiguration

logger = logging.getLogger("ajun.auth.service")

GENERIC_AUTH_ERROR = "Invalid or unverified authentication credentials"


# --- HS256 JWT Implementation (No external unpinned dependencies) ---

def _b64_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _b64_decode(data: str) -> bytes:
    remainder = len(data) % 4
    if remainder > 0:
        data += "=" * (4 - remainder)
    return base64.urlsafe_b64decode(data)


def create_access_token(user_id: uuid.UUID, email: Optional[str] = None) -> str:
    """Creates a short-lived HS256 JWT access token (15 minutes)."""
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": str(user_id),
        "email": email or "",
        "exp": int(expire.timestamp()),
        "iat": int(now.timestamp()),
    }
    
    header_b64 = _b64_encode(json.dumps(header).encode("utf-8"))
    payload_b64 = _b64_encode(json.dumps(payload).encode("utf-8"))
    signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
    
    signature = hmac.new(settings.JWT_SECRET.encode("utf-8"), signing_input, hashlib.sha256).digest()
    signature_b64 = _b64_encode(signature)
    
    return f"{header_b64}.{payload_b64}.{signature_b64}"


def decode_access_token(token: str) -> dict:
    """Verifies HS256 signature and returns payload, rejecting expired or tampered tokens."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("Invalid JWT format")
        
        header_b64, payload_b64, signature_b64 = parts
        signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
        
        expected_sig = hmac.new(settings.JWT_SECRET.encode("utf-8"), signing_input, hashlib.sha256).digest()
        actual_sig = _b64_decode(signature_b64)
        
        if not hmac.compare_digest(expected_sig, actual_sig):
            raise ValueError("Invalid JWT signature")
        
        payload = json.loads(_b64_decode(payload_b64).decode("utf-8"))
        
        now_ts = int(datetime.now(timezone.utc).timestamp())
        if payload.get("exp", 0) < now_ts:
            raise ValueError("JWT token expired")
        
        return payload
    except Exception as e:
        logger.warning("Access token validation failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=GENERIC_AUTH_ERROR,
            headers={"WWW-Authenticate": "Bearer"},
        )


# --- Pure Campus Domain Matcher ---

def verify_campus_domain(email: str, allowed_domains: List[str]) -> bool:
    """Pure function validating institutional campus domain with exact or dot-boundary rules.
    
    Matches:
      - 'user@ui.ac.id' -> True
      - 'student@cs.ui.ac.id' -> True
    Strictly Rejects Spoofing:
      - 'attacker@evil-ui.ac.id' -> False
      - 'attacker@fakeui.ac.id' -> False
      - 'attacker@ui.ac.id.evil.com' -> False
    """
    if not email or "@" not in email:
        return False
    
    parts = email.split("@")
    if len(parts) != 2:
        return False
        
    email_domain = parts[1].strip().lower()
    if not email_domain:
        return False

    for allowed in allowed_domains:
        norm_allowed = allowed.strip().lower()
        if not norm_allowed:
            continue
        if email_domain == norm_allowed or email_domain.endswith("." + norm_allowed):
            return True
    return False


async def get_allowed_campus_domains(db: AsyncSession) -> List[str]:
    """Retrieves allowed campus domains from system_configurations table."""
    stmt = select(SystemConfiguration).where(SystemConfiguration.key == "ALLOWED_CAMPUS_DOMAINS")
    result = await db.execute(stmt)
    config = result.scalar_one_or_none()
    raw = config.value if config else "ui.ac.id,ugm.ac.id,itb.ac.id"
    return [d.strip().lower() for d in raw.split(",") if d.strip()]


# --- User Authentication (Lookup by google_sub ONLY) ---

async def authenticate_google_user(db: AsyncSession, payload: dict) -> Tuple[User, bool]:
    """Authenticates or creates a user using verified Google claims.
    
    Phase 1a Rules:
    - User lookup is done by google_sub ONLY. Never by email.
    - If a user with a different google_sub already claims the same email, reject with 409 Conflict.
    - If user exists: refresh email and full_name from token.
    - In Phase 1a: DO NOT set is_identity_verified or campus_verified_at.
    - Returns (user, campus_domain_match: bool).
    """
    google_sub = str(payload["sub"]).strip()
    email = str(payload["email"]).strip().lower()
    full_name = payload.get("name")

    allowed_domains = await get_allowed_campus_domains(db)
    campus_domain_match = verify_campus_domain(email, allowed_domains)

    # 1. Lookup user by google_sub ONLY
    stmt = select(User).where(User.google_sub == google_sub)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if user:
        if user.deleted_at is not None:
            logger.warning("Login rejected for deleted account: google_sub=%s", google_sub)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is deactivated.",
            )
        
        # If email changed in token, check for UNIQUE(email) conflict with any other user
        if user.email != email:
            conflict_stmt = select(User).where(User.email == email, User.id != user.id)
            conflict_res = await db.execute(conflict_stmt)
            if conflict_res.scalar_one_or_none():
                logger.warning("Email conflict on refresh: %s already taken by another sub", email)
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Email address is already associated with another account.",
                )
            user.email = email
            
        if full_name:
            user.full_name = full_name
    else:
        # Check if email is already taken by an existing user with a different google_sub
        conflict_stmt = select(User).where(User.email == email)
        conflict_res = await db.execute(conflict_stmt)
        if conflict_res.scalar_one_or_none():
            logger.warning("Registration conflict: email %s already registered to different sub", email)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email address is already associated with another account.",
            )

        # Create new user: Phase 1a keeps is_identity_verified as False
        user = User(
            id=uuid.uuid4(),
            google_sub=google_sub,
            email=email,
            full_name=full_name,
            is_identity_verified=False,
            campus_verified_at=None,
            campus_verification_method=None,
            created_at=datetime.now(timezone.utc),
        )
        db.add(user)

    await db.commit()
    await db.refresh(user)
    return user, campus_domain_match


# --- Refresh Token Management (Race-Safe Atomic Rotation & Whole Family Revocation) ---

async def create_refresh_token(
    db: AsyncSession,
    user_id: uuid.UUID,
    family_id: Optional[uuid.UUID] = None,
) -> Tuple[str, RefreshToken]:
    """Generates a cryptographic 256-bit random refresh token and stores its SHA-256 hash."""
    raw_token = secrets.token_urlsafe(32)  # 256-bit entropy
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    if family_id is None:
        family_id = uuid.uuid4()

    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    db_token = RefreshToken(
        id=uuid.uuid4(),
        user_id=user_id,
        token_hash=token_hash,
        family_id=family_id,
        expires_at=expires_at,
        created_at=datetime.now(timezone.utc),
    )
    db.add(db_token)
    await db.commit()
    await db.refresh(db_token)

    return raw_token, db_token


async def rotate_refresh_token(db: AsyncSession, raw_token: str) -> Tuple[str, str, User]:
    """Rotates refresh token using one atomic statement.
    
    1. Executes atomic conditional update:
       UPDATE refresh_tokens SET used_at = now()
       WHERE token_hash = :h AND used_at IS NULL AND revoked_at IS NULL AND expires_at > now()
    
    2. Checks affected row count:
       - If rowcount == 1: atomic win! Issues new token pair with same family_id.
       - If rowcount == 0:
         Checks if token exists: if it exists and was already used or revoked,
         revokes the WHOLE family immediately and returns 401. Otherwise returns 401.
    """
    token_hash = hashlib.sha256(raw_token.strip().encode("utf-8")).hexdigest()
    now = datetime.now(timezone.utc)

    # Atomic statement: exactly one concurrent request can transition used_at from NULL to now()
    atomic_update = (
        update(RefreshToken)
        .where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.used_at.is_(None),
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > now,
        )
        .values(used_at=now)
    )
    result = await db.execute(atomic_update)
    rows_affected = result.rowcount

    if rows_affected == 1:
        # Atomic rotation successful! Read the token to get family_id and user_id
        stmt_read = select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        read_res = await db.execute(stmt_read)
        current_token = read_res.scalar_one()

        stmt_user = select(User).where(User.id == current_token.user_id)
        user_res = await db.execute(stmt_user)
        user = user_res.scalar_one()

        if user.deleted_at is not None:
            raise HTTPException(status_code=401, detail=GENERIC_AUTH_ERROR)

        # Issue new pair within the SAME family_id
        new_access = create_access_token(user.id, user.email)
        new_raw_refresh, _ = await create_refresh_token(db, user.id, family_id=current_token.family_id)

        await db.commit()
        return new_access, new_raw_refresh, user

    # Rows affected is 0: Token is invalid, expired, revoked, or reuse attempt!
    stmt_check = select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    check_res = await db.execute(stmt_check)
    existing_token = check_res.scalar_one_or_none()

    if existing_token is not None:
        # If token exists and was already used or revoked: REUSE DETECTED!
        if existing_token.used_at is not None or existing_token.revoked_at is not None:
            logger.warning("Token reuse detected for family_id %s. Revoking whole family.", existing_token.family_id)
            revoke_family = (
                update(RefreshToken)
                .where(RefreshToken.family_id == existing_token.family_id)
                .values(revoked_at=now)
            )
            await db.execute(revoke_family)
            await db.commit()

    raise HTTPException(status_code=401, detail=GENERIC_AUTH_ERROR)


async def revoke_user_family_by_token(db: AsyncSession, raw_token: str) -> None:
    """Revokes caller's whole refresh-token family upon logout."""
    token_hash = hashlib.sha256(raw_token.strip().encode("utf-8")).hexdigest()
    stmt = select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    result = await db.execute(stmt)
    token = result.scalar_one_or_none()

    if token:
        now = datetime.now(timezone.utc)
        revoke_family = (
            update(RefreshToken)
            .where(RefreshToken.family_id == token.family_id)
            .values(revoked_at=now)
        )
        await db.execute(revoke_family)
        await db.commit()
