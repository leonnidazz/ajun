import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy import select

from app.config import settings, get_cors_allowed_origins
from app.database import engine, AsyncSessionLocal
from app.models.configuration import SystemConfiguration
from app.api.v1.router import api_v1_router

logger = logging.getLogger("ajun.backend")

MAX_REQUEST_BODY_BYTES = 1024 * 1024  # 1 MB Limit


class RequestBodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Enforces strict 1 MB maximum request body size limit."""
    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > MAX_REQUEST_BODY_BYTES:
                    return Response(
                        content='{"detail": "Request payload too large (max 1 MB)."}',
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        media_type="application/json",
                    )
            except ValueError:
                pass
        return await call_next(request)


async def check_startup_invariants(session_factory=None):
    """Reads configuration from database and verifies system invariants without modifying data.
    
    Startup FAILS with RuntimeError if:
    - REOPEN_MIN_LEAD_MINUTES < MIN_CONFIRMATION_LEAD_MINUTES
    - Any required lead time config is missing
    """
    factory = session_factory if session_factory is not None else AsyncSessionLocal
    async with factory() as session:
        stmt_reopen = select(SystemConfiguration).where(SystemConfiguration.key == "REOPEN_MIN_LEAD_MINUTES")
        stmt_min_conf = select(SystemConfiguration).where(SystemConfiguration.key == "MIN_CONFIRMATION_LEAD_MINUTES")
        
        reopen_res = await session.execute(stmt_reopen)
        min_conf_res = await session.execute(stmt_min_conf)
        
        reopen_obj = reopen_res.scalar_one_or_none()
        min_conf_obj = min_conf_res.scalar_one_or_none()
        
        if not reopen_obj or not min_conf_obj:
            raise RuntimeError(
                "Startup invariant check failed: Required configuration keys "
                "REOPEN_MIN_LEAD_MINUTES or MIN_CONFIRMATION_LEAD_MINUTES are missing in database. "
                "Please run 'alembic upgrade head' to apply migrations."
            )
        
        reopen_val = int(reopen_obj.value)
        min_conf_val = int(min_conf_obj.value)
        
        if reopen_val < min_conf_val:
            raise RuntimeError(
                f"Startup invariant check failed: REOPEN_MIN_LEAD_MINUTES ({reopen_val}) < "
                f"MIN_CONFIRMATION_LEAD_MINUTES ({min_conf_val}). Startup halted."
            )
            
        logger.info(
            "Startup invariant verified: REOPEN_MIN_LEAD_MINUTES (%s) >= MIN_CONFIRMATION_LEAD_MINUTES (%s).",
            reopen_val,
            min_conf_val,
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Check configuration invariants (fail fast if violated)
    logger.info("Initializing Ajun Backend API...")
    await check_startup_invariants()
    yield
    # Shutdown
    logger.info("Disposing database connections...")
    await engine.dispose()


app = FastAPI(
    title="Ajun API (Antar Jemput Universitas)",
    description="Backend API platform pencocokan tumpangan sesama mahasiswa (Phase 1a).",
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

# Request body size limit middleware (1 MB limit)
app.add_middleware(RequestBodySizeLimitMiddleware)

# Strict CORS: never "*", strictly from CORS_ALLOWED_ORIGINS
allowed_origins = get_cors_allowed_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# Mount single canonical API v1 route prefix
app.include_router(api_v1_router)


@app.get("/health", tags=["Health"])
async def health_check():
    """Unprefixed health check endpoint."""
    return {
        "status": "ok",
        "app": "Ajun",
        "version": settings.APP_VERSION,
        "phase": "Phase 1a",
    }
