from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.auth import router as auth_router
from app.api.routes.generate import router as generate_router
from app.api.routes.health import router as health_router
from app.api.routes.history import router as history_router
from app.api.routes.preferences import router as preferences_router
from app.config import settings
from app.db.engine import engine
from app.db.models import Base
from app.db.redis import init_redis, close_redis
from app.api.middleware.pipeline import (
    RequestIDMiddleware,
    ErrorHandlerMiddleware,
)
from app.api.middleware.rate_limit import setup_rate_limiter
from app.mcp.client import close_code_analysis_client
from app.tracing.tracer import setup_langsmith

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

setup_langsmith()


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await init_redis()

    from app.scheduler.jobs import scheduler
    scheduler.start()

    yield

    scheduler.shutdown(wait=False)
    await close_code_analysis_client()
    await close_redis()
    await engine.dispose()


app = FastAPI(
    title="AutoJudge",
    description="多维对抗式代码进化引擎",
    version="0.5.0",
    lifespan=lifespan,
)

app.add_middleware(ErrorHandlerMiddleware)
app.add_middleware(RequestIDMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

setup_rate_limiter(app)

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(generate_router)
app.include_router(history_router)
app.include_router(preferences_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=9000,
        reload=settings.debug,
    )
