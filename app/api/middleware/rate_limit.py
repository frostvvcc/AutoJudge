"""
Sliding-window rate limiting via slowapi.

slowapi wraps the `limits` library, which implements proper sliding-window
counters on Redis — no fixed-window boundary exploits.

Limits applied:
  - /api/v1/generate*:   5/minute, 30/hour, 100/day  (compute-intensive debate)
  - /api/v1/auth/login:  10/minute                    (brute-force protection)
  - Other API endpoints: 60/minute                    (general protection)
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.config import settings

logger = logging.getLogger(__name__)


def _key_func(request: Request) -> str:
    """Extract rate-limit key: prefer JWT subject, fall back to IP."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer ") and len(auth) > 23:
        return f"user:{auth[7:23]}"
    return get_remote_address(request)


limiter = Limiter(
    key_func=_key_func,
    storage_uri=settings.redis_url,
    strategy="moving-window",
)


def _rate_limit_exceeded_handler(
    request: Request, exc: RateLimitExceeded
) -> Response:
    retry_after = getattr(exc, "retry_after", 60)
    logger.warning(
        "rate_limit_exceeded key=%s detail=%s",
        _key_func(request),
        str(exc.detail),
    )
    return JSONResponse(
        status_code=429,
        content={"detail": f"Rate limit exceeded: {exc.detail}"},
        headers={"Retry-After": str(retry_after)},
    )


def setup_rate_limiter(app: FastAPI) -> None:
    """Attach slowapi limiter to the FastAPI app."""
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
