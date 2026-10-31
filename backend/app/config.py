import os
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(__file__), "..", ".env"),
        extra="allow",
    )

    APP_NAME: str = "Ajun Backend"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"

    # Database URLs (Strictly PostgreSQL Asyncpg)
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres@localhost:5432/ajun_dev")
    DATABASE_URL_TEST: str = os.getenv("DATABASE_URL_TEST", "postgresql+asyncpg://postgres@localhost:5432/ajun_test")

    # JWT & Secrets (MANDATORY: Minimum 32 characters)
    JWT_SECRET: str = os.getenv("JWT_SECRET", "ajun_dev_super_secret_jwt_key_2026_random_secure_32_chars_long")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
    REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "30"))

    # System Secrets
    TOMBSTONE_HMAC_SECRET: str = os.getenv("TOMBSTONE_HMAC_SECRET", "ajun_dev_tombstone_hmac_secret_32_chars_long_now")
    CRON_SECRET: str = os.getenv("CRON_SECRET", "ajun_dev_cron_secret_sweeper_2026_secure")
    ADMIN_EMAILS: str = os.getenv("ADMIN_EMAILS", "admin@ui.ac.id,superadmin@ugm.ac.id")

    # CORS (Strictly explicit list, NEVER "*")
    CORS_ALLOWED_ORIGINS: str = os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")

    # Google OAuth Client IDs (Accepted Audiences)
    GOOGLE_CLIENT_IDS: str = os.getenv("GOOGLE_CLIENT_IDS", "mock-client-id-web,mock-client-id-android")

    # Service Fee & Payment Flags
    SERVICE_FEE_COINS: int = int(os.getenv("SERVICE_FEE_COINS", "1"))
    PAYMENT_ENV: str = os.getenv("PAYMENT_ENV", "sandbox")
    TOPUP_ENABLED: bool = os.getenv("TOPUP_ENABLED", "false").lower() in ("true", "1", "yes")

    # Rate Limiting
    AUTH_RATE_LIMIT_PER_MINUTE: int = int(os.getenv("AUTH_RATE_LIMIT_PER_MINUTE", "10"))
    LOGOUT_RATE_LIMIT_PER_MINUTE: int = int(os.getenv("LOGOUT_RATE_LIMIT_PER_MINUTE", "20"))


settings = Settings()


def validate_settings():
    """Enforces startup security invariants on configuration."""
    if len(settings.JWT_SECRET) < 32:
        raise ValueError(f"Startup validation failed: JWT_SECRET must be at least 32 characters long (got {len(settings.JWT_SECRET)}).")

    origins = get_cors_allowed_origins()
    if "*" in origins:
        raise ValueError("Startup validation failed: CORS_ALLOWED_ORIGINS cannot contain wildcard '*' per security policy.")

    if not settings.DATABASE_URL.startswith("postgresql"):
        raise ValueError("Startup validation failed: Database must be PostgreSQL (DATABASE_URL must start with 'postgresql').")


def get_admin_emails() -> List[str]:
    """Returns normalized lowercase list of admin emails."""
    raw = settings.ADMIN_EMAILS
    if not raw:
        return []
    return [email.strip().lower() for email in raw.split(",") if email.strip()]


def is_admin_email(email: str | None) -> bool:
    """Checks whether the given email address is authorized as an administrator."""
    if not email:
        return False
    return email.strip().lower() in get_admin_emails()


def get_cors_allowed_origins() -> List[str]:
    """Parses and returns list of allowed CORS origins."""
    raw = settings.CORS_ALLOWED_ORIGINS
    if not raw:
        return []
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def get_google_client_ids() -> List[str]:
    """Parses and returns list of allowed Google Client IDs (audiences)."""
    raw = settings.GOOGLE_CLIENT_IDS
    if not raw:
        return []
    return [cid.strip() for cid in raw.split(",") if cid.strip()]


# Validate settings upon module import
validate_settings()
