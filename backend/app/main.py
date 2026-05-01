import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # Startup: ensure MinIO bucket exists
    from app.core.storage import storage_service

    try:
        await storage_service.ensure_bucket()
    except Exception as e:
        logger.warning(f"MinIO not ready yet: {e}")

    # Detect Chinese FTS config
    try:
        from app.api.search import _detect_fts_config
        from app.db.base import async_session

        async with async_session() as db:
            await _detect_fts_config(db)
    except Exception as e:
        logger.warning(f"FTS config detection failed: {e}")

    yield
    # Shutdown: cleanup if needed


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten in production
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Register API routers ──────────────────────────────────

from app.api.documents import router as documents_router
from app.api.search import router as search_router
from app.api.relations import router as relations_router
from app.api.upload import router as upload_router

app.include_router(documents_router, prefix="/api/documents", tags=["documents"])
app.include_router(search_router, prefix="/api/search", tags=["search"])
app.include_router(relations_router, prefix="/api/relations", tags=["relations"])
app.include_router(upload_router, prefix="/api/upload", tags=["upload"])


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "service": settings.app_name}
