"""
Middleware pipeline — modeled after AutoResearch's 9-layer chain.

AutoResearch: RequestID → Log → SecHeaders → Error → RateLimit → Auth → Tenant → DB Session → Audit
AutoJudge:    RequestID → Log → SecHeaders → Error → RateLimit → Auth → AuditLog

Dropped: Tenant (single-tenant), DB Session (handled by Depends).
"""

from __future__ import annotations

import logging
import time
import uuid

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", uuid.uuid4().hex)
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


class StructuredLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.monotonic()
        response = await call_next(request)
        duration_ms = int((time.monotonic() - start) * 1000)

        request_id = getattr(request.state, "request_id", "-")
        logger.info(
            "http_request method=%s path=%s status=%d duration_ms=%d request_id=%s",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            request_id,
        )
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        except Exception as exc:
            request_id = getattr(request.state, "request_id", "-")
            logger.error(
                "unhandled_error request_id=%s path=%s error=%s",
                request_id, request.url.path, exc,
                exc_info=True,
            )
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=500,
                content={
                    "detail": "Internal server error",
                    "request_id": request_id,
                },
            )


class AuditLogMiddleware(BaseHTTPMiddleware):
    """Log mutating requests to the audit_logs table."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        if request.method in ("POST", "PUT", "DELETE", "PATCH"):
            request_id = getattr(request.state, "request_id", "-")
            user_id = getattr(request.state, "user_id", None)
            try:
                from app.db.engine import async_session
                from app.db.models import AuditLog

                async with async_session() as db:
                    db.add(AuditLog(
                        request_id=request_id,
                        user_id=user_id,
                        method=request.method,
                        path=str(request.url.path),
                        status_code=response.status_code,
                        ip_address=request.client.host if request.client else None,
                    ))
                    await db.commit()
            except Exception as exc:
                logger.warning("audit_log_failed request_id=%s error=%s", request_id, exc)

        return response
