"""In-memory sliding-window rate limiter for Ajun Authentication.

SECURITY & ARCHITECTURAL TRADEOFF DOCUMENTATION:
1. Per-Process Memory Scope:
   This limiter tracks request timestamps in process memory. If multiple worker processes
   or servers run in production, rate limits are enforced per-worker rather than globally.
   For multi-instance distributed deployments, a shared store (such as Redis) should be used.

2. Client IP & X-Forwarded-For Spoofing Risk:
   Client IP is extracted from the connection host. If deployed behind a reverse proxy
   (e.g., Nginx, Cloud Run, Render), the proxy MUST be configured to overwrite or strip
   untrusted client X-Forwarded-For headers to prevent attackers from spoofing their IP.
"""

import time
from collections import defaultdict
from typing import Dict, List
from fastapi import Request, HTTPException, status

from app.config import settings


class InMemorySlidingWindowRateLimiter:
    def __init__(self, requests_limit: int = 10, window_seconds: int = 60, name: str = "auth"):
        self.requests_limit = requests_limit
        self.window_seconds = window_seconds
        self.name = name
        self.ip_records: Dict[str, List[float]] = defaultdict(list)

    def check_rate_limit(self, client_ip: str) -> None:
        now = time.time()
        window_start = now - self.window_seconds
        
        # Purge timestamps outside the sliding window
        valid_timestamps = [ts for ts in self.ip_records[client_ip] if ts > window_start]
        self.ip_records[client_ip] = valid_timestamps

        if len(valid_timestamps) >= self.requests_limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded: Maximum {self.requests_limit} requests per minute.",
                headers={"Retry-After": str(self.window_seconds)},
            )

        self.ip_records[client_ip].append(now)

    def reset(self):
        """Resets tracking records (used for test isolation)."""
        self.ip_records.clear()


# 1. Limiter for sensitive login & refresh endpoints (10 req/min per IP)
auth_rate_limiter = InMemorySlidingWindowRateLimiter(
    requests_limit=settings.AUTH_RATE_LIMIT_PER_MINUTE,
    window_seconds=60,
    name="login_refresh",
)

# 2. Separate limiter for logout endpoint (20 req/min per IP)
logout_rate_limiter = InMemorySlidingWindowRateLimiter(
    requests_limit=settings.LOGOUT_RATE_LIMIT_PER_MINUTE,
    window_seconds=60,
    name="logout",
)


def _get_client_ip(request: Request) -> str:
    # Use direct client connection IP to prevent header spoofing unless proxy is trusted
    return request.client.host if request.client else "127.0.0.1"


async def rate_limit_auth_dependency(request: Request) -> None:
    """Enforces 10 req/min rate limit on login & refresh endpoints."""
    client_ip = _get_client_ip(request)
    auth_rate_limiter.check_rate_limit(client_ip)


async def rate_limit_logout_dependency(request: Request) -> None:
    """Enforces separate rate limit on logout endpoint."""
    client_ip = _get_client_ip(request)
    logout_rate_limiter.check_rate_limit(client_ip)
