from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes.generate import router as generate_router
from app.api.routes.health import router as health_router
from app.api.middleware.auth import AuthMiddleware
from app.tracing.tracer import setup_langsmith
from app.config import settings

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

setup_langsmith()

app = FastAPI(
    title="AutoJudge",
    description="多维对抗式代码进化引擎",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

auth_middleware = AuthMiddleware()


@app.middleware("http")
async def auth_and_rate_limit(request: Request, call_next):
    if request.url.path.startswith("/api/v1/generate"):
        try:
            api_key = await auth_middleware.authenticate(request)
            await auth_middleware.check_rate_limit(api_key)
            request.state.api_key = api_key
        except Exception as e:
            return JSONResponse(
                status_code=getattr(e, "status_code", 401),
                content={"detail": str(getattr(e, "detail", e))},
            )
    return await call_next(request)


app.include_router(health_router)
app.include_router(generate_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=9000,
        reload=settings.debug,
    )
