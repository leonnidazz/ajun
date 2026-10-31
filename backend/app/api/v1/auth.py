from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.schemas.auth import GoogleLoginRequest, TokenResponse, RefreshTokenRequest
from app.schemas.user import UserResponse
from app.services.google_token_verifier import verify_google_id_token
from app.services.auth_service import (
    authenticate_google_user,
    create_access_token,
    create_refresh_token,
    rotate_refresh_token,
    revoke_user_family_by_token,
    verify_campus_domain,
    get_allowed_campus_domains,
)
from app.utils.rate_limiter import (
    rate_limit_auth_dependency,
    rate_limit_logout_dependency,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _to_user_response(user: User, campus_domain_match: bool) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        campus_name=user.campus_name,
        campus_domain_match=campus_domain_match,
        created_at=user.created_at,
    )


@router.post(
    "/google-login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(rate_limit_auth_dependency)],
)
async def google_login(
    payload: GoogleLoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """Authenticates student via Google ID Token using official google-auth.
    
    - Validates signature against Google's certificates, aud in GOOGLE_CLIENT_IDS, and email_verified == True.
    - Looks up user by google_sub ONLY.
    - In Phase 1a: computes campus_domain_match without updating is_identity_verified.
    - Generates HS256 access token (15 mins) and opaque cryptographic refresh token (family root).
    """
    google_claims = verify_google_id_token(payload.id_token)
    user, campus_domain_match = await authenticate_google_user(db, google_claims)

    access_token = create_access_token(user.id, user.email)
    raw_refresh_token, _ = await create_refresh_token(db, user.id)

    return TokenResponse(
        access_token=access_token,
        refresh_token=raw_refresh_token,
        token_type="bearer",
        user=_to_user_response(user, campus_domain_match),
    )


@router.post(
    "/refresh",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(rate_limit_auth_dependency)],
)
async def refresh_tokens(
    payload: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
):
    """Race-safe atomic refresh token rotation.
    
    If reuse is detected, revokes the whole token family immediately and returns 401.
    """
    new_access_token, new_refresh_token, user = await rotate_refresh_token(db, payload.refresh_token)

    allowed_domains = await get_allowed_campus_domains(db)
    campus_match = verify_campus_domain(user.email, allowed_domains) if user.email else False

    return TokenResponse(
        access_token=new_access_token,
        refresh_token=new_refresh_token,
        token_type="bearer",
        user=_to_user_response(user, campus_match),
    )


@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(rate_limit_logout_dependency)],
)
async def logout(
    payload: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
):
    """Revokes the caller's entire refresh token family."""
    await revoke_user_family_by_token(db, payload.refresh_token)
    return {"message": "Logged out successfully"}
