from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core.config import get_settings
from app.core.database import close_mongo, connect_to_mongo, get_database
from app.core.logging_config import configure_logging
from app.core.rate_limit import InMemoryRateLimitMiddleware
from app.services.analysis_engine import AnalysisEngine
from app.services.speech_service import SpeechService

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.settings = settings

    db = None
    try:
        await connect_to_mongo(settings)
        db = get_database()
    except Exception as exc:
        logger.warning("MongoDB is unavailable; continuing without cache/log persistence: %s", exc)

    app.state.analysis_engine = AnalysisEngine(settings, db)
    app.state.speech_service = SpeechService(settings)
    yield
    await close_mongo()


settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="Medicine identification and safety information with OCR, speech, drug APIs, and RAG.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(
    InMemoryRateLimitMiddleware,
    requests=settings.rate_limit_requests,
    window_seconds=settings.rate_limit_window_seconds,
)

app.include_router(router, prefix=settings.api_prefix)


@app.get("/")
async def root() -> dict[str, str]:
    return {"app": settings.app_name, "health": f"{settings.api_prefix}/health"}
