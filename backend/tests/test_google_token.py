import hmac
import hashlib
import pytest
from fastapi import HTTPException
from app.services.google_token_verifier import verify_google_id_token, GENERIC_UNAUTHORIZED_MESSAGE
from tests.conftest import create_test_id_token, TEST_PUBLIC_KEY_PEM, _b64_url_encode


def test_verify_valid_rsa_token_https_issuer():
    token = create_test_id_token(
        sub="google-sub-valid-1",
        email="student@ui.ac.id",
        name="Valid Student",
        iss="https://accounts.google.com",
    )
    payload = verify_google_id_token(token)
    assert payload["sub"] == "google-sub-valid-1"
    assert payload["email"] == "student@ui.ac.id"
    assert payload["email_verified"] is True


def test_verify_valid_rsa_token_accounts_google_com_issuer():
    token = create_test_id_token(
        sub="google-sub-valid-2",
        email="student@ugm.ac.id",
        iss="accounts.google.com",
    )
    payload = verify_google_id_token(token)
    assert payload["sub"] == "google-sub-valid-2"
    assert payload["iss"] == "accounts.google.com"


def test_reject_forged_rsa_signature():
    token = create_test_id_token(forge_signature=True)
    with pytest.raises(HTTPException) as exc:
        verify_google_id_token(token)
    assert exc.value.status_code == 401
    assert exc.value.detail == GENERIC_UNAUTHORIZED_MESSAGE


def test_reject_expired_token():
    token = create_test_id_token(exp_offset_seconds=-3600)
    with pytest.raises(HTTPException) as exc:
        verify_google_id_token(token)
    assert exc.value.status_code == 401
    assert exc.value.detail == GENERIC_UNAUTHORIZED_MESSAGE


def test_reject_wrong_audience():
    token = create_test_id_token(aud="unrecognized-client-id-xyz")
    with pytest.raises(HTTPException) as exc:
        verify_google_id_token(token)
    assert exc.value.status_code == 401
    assert exc.value.detail == GENERIC_UNAUTHORIZED_MESSAGE


def test_reject_wrong_issuer():
    token = create_test_id_token(iss="https://evil-identity.com")
    with pytest.raises(HTTPException) as exc:
        verify_google_id_token(token)
    assert exc.value.status_code == 401
    assert exc.value.detail == GENERIC_UNAUTHORIZED_MESSAGE


def test_reject_email_verified_false():
    token = create_test_id_token(email_verified=False)
    with pytest.raises(HTTPException) as exc:
        verify_google_id_token(token)
    assert exc.value.status_code == 401
    assert exc.value.detail == GENERIC_UNAUTHORIZED_MESSAGE


def test_reject_missing_sub():
    token = create_test_id_token(sub=None)
    with pytest.raises(HTTPException) as exc:
        verify_google_id_token(token)
    assert exc.value.status_code == 401
    assert exc.value.detail == GENERIC_UNAUTHORIZED_MESSAGE


def test_reject_missing_email():
    token = create_test_id_token(email=None)
    with pytest.raises(HTTPException) as exc:
        verify_google_id_token(token)
    assert exc.value.status_code == 401
    assert exc.value.detail == GENERIC_UNAUTHORIZED_MESSAGE


def test_reject_alg_none():
    token = create_test_id_token(alg="none")
    with pytest.raises(HTTPException) as exc:
        verify_google_id_token(token)
    assert exc.value.status_code == 401
    assert exc.value.detail == GENERIC_UNAUTHORIZED_MESSAGE


def test_reject_hs256_signed_with_public_key():
    """Attack scenario: Attacker crafts HS256 token signed with RSA public key."""
    h_b64 = _b64_url_encode(b'{"alg":"HS256","typ":"JWT"}')
    p_b64 = _b64_url_encode(b'{"sub":"hacker","email":"hacker@evil.com","email_verified":true,"iss":"https://accounts.google.com","aud":"mock-client-id-web","exp":9999999999}')
    signing_input = f"{h_b64}.{p_b64}".encode("utf-8")
    
    forged_sig = hmac.new(TEST_PUBLIC_KEY_PEM.encode("utf-8"), signing_input, hashlib.sha256).digest()
    forged_token = f"{h_b64}.{p_b64}.{_b64_url_encode(forged_sig)}"

    with pytest.raises(HTTPException) as exc:
        verify_google_id_token(forged_token)
    assert exc.value.status_code == 401
    assert exc.value.detail == GENERIC_UNAUTHORIZED_MESSAGE
