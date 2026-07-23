from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from contextlib import asynccontextmanager
from app.core.config import get_settings, validate_phi_encryption_key
from app.core.logging import get_logger

settings = get_settings()
log = get_logger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Fail fast if PHI_ENCRYPTION_KEY is missing/invalid
    try:
        validate_phi_encryption_key(settings)
    except RuntimeError as exc:
        log.error("phi_encryption_key_validation_failed", reason=str(exc))
        raise

    # Create DB tables on startup (dev convenience; use Alembic in production)
    try:
        from app.services.database import create_all_tables
        await create_all_tables()
        log.info("database_tables_created_or_verified")
    except Exception as exc:
        log.warning("database_init_failed", reason=str(exc))

    yield
    # Cleanup actions

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health_check():
    return {"status": "ok", "app": settings.app_name, "version": settings.app_version}

# Include API Routers
from app.api.v1.api import api_router
app.include_router(api_router, prefix="/api/v1")

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=settings.debug)