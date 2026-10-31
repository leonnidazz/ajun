import logging
from typing import Dict, Any, Optional
from fastapi import HTTPException, status
from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_requests

from app.config import get_google_client_ids

logger = logging.getLogger("ajun.auth.verifier")

GENERIC_UNAUTHORIZED_MESSAGE = "Invalid or unverified authentication credentials"


class GoogleTokenVerificationError(HTTPException):
    def __init__(self, internal_reason: str):
        # Log the internal reason for audit/debugging WITHOUT logging the actual token
        logger.warning("Google token verification failed: %s", internal_reason)
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=GENERIC_UNAUTHORIZED_MESSAGE,
            headers={"WWW-Authenticate": "Bearer"},
        )


def verify_google_id_token(
    id_token_str: str,
    request_adapter: Optional[google_requests.Request] = None,
) -> Dict[str, Any]:
    """Verifies a Google ID Token using official google-auth library.
    
    Validates:
    - RSA signature against Google public certificates (or patched certs in tests)
    - Token expiration (exp)
    - Issuer: 'accounts.google.com' or 'https://accounts.google.com'
    - Audience: matching one of the configured GOOGLE_CLIENT_IDS
    - Subject (sub): non-empty
    - Email claim: non-empty
    - email_verified: MUST be True
    
    Every failure returns the exact same generic 401 error response.
    """
    if not id_token_str or not isinstance(id_token_str, str) or not id_token_str.strip():
        raise GoogleTokenVerificationError("Empty or invalid token format")

    token = id_token_str.strip()

    if request_adapter is None:
        request_adapter = google_requests.Request()

    allowed_audiences = get_google_client_ids()

    # Step 1: Verify cryptographic signature and standard claims using google-auth
    # Try against each allowed audience if configured
    verified_payload = None
    last_error_reason = "No audience matched"

    audiences_to_try = allowed_audiences if allowed_audiences else [None]

    for aud in audiences_to_try:
        try:
            payload = google_id_token.verify_oauth2_token(
                token,
                request_adapter,
                audience=aud,
            )
            verified_payload = payload
            break
        except Exception as e:
            last_error_reason = str(e)

    if not verified_payload:
        raise GoogleTokenVerificationError(f"Library validation error: {last_error_reason}")

    # Step 2: Validate issuer (must be accounts.google.com or https://accounts.google.com)
    iss = verified_payload.get("iss")
    if iss not in ("accounts.google.com", "https://accounts.google.com"):
        raise GoogleTokenVerificationError(f"Invalid issuer: {iss}")

    # Step 3: Validate subject claim
    sub = verified_payload.get("sub")
    if not sub or not str(sub).strip():
        raise GoogleTokenVerificationError("Missing 'sub' claim")

    # Step 4: Validate email claim
    email = verified_payload.get("email")
    if not email or not str(email).strip():
        raise GoogleTokenVerificationError("Missing 'email' claim")

    # Step 5: Enforce email_verified == True (MANDATORY)
    email_verified = verified_payload.get("email_verified")
    if email_verified is not True:
        raise GoogleTokenVerificationError(f"Email not verified (email_verified={email_verified})")

    return verified_payload
