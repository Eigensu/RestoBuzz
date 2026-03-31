from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.database import init_indexes, close_db
from app.core.logging import setup_logging, CorrelationIdMiddleware, get_logger
from app.core.errors import AppError
from app.config import settings
from app.routers import (
    auth,
    campaigns,
    contacts,
    templates,
    webhooks,
    inbox,
    settings as settings_router,
    health,
    members,
    media,
    restaurants,
)
from app.sse.campaign_stream import router as sse_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger = get_logger(__name__)
    logger.info("backend_startup", version="1.0.0", status="loading_indexes")
    await init_indexes()
    logger.info("backend_startup_complete")
    yield
    await close_db()


app = FastAPI(
    title="WhatsApp Bulk Sender API",
    version="1.0.0",
    lifespan=lifespan,
    redirect_slashes=False,
)

# IMPORTANT: Starlette runs middleware in REVERSE registration order (LIFO).
# CorrelationIdMiddleware must be registered FIRST so that CORSMiddleware
# executes OUTERMOST — i.e. it handles preflight OPTIONS before anything else.
app.add_middleware(CorrelationIdMiddleware)

# Enhanced CORS: If '*' is in origins, allow any origin but disable credentials to avoid
# insecure wildcard configuration. For specific origins, credentials remain enabled.
_origins = settings.cors_origins_list
if "*" in _origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.exception_handler(AppError)
async def app_error_handler(_request: Request, exc: AppError):
    return JSONResponse(status_code=exc.status_code, content=exc.to_dict())


@app.exception_handler(Exception)
async def global_exception_handler(_request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "type": "server_error"},
    )


# Mount routers
app.include_router(auth.router, prefix="/api")
app.include_router(campaigns.router, prefix="/api")
app.include_router(contacts.router, prefix="/api")
app.include_router(templates.router, prefix="/api")
app.include_router(webhooks.router, prefix="/api")
app.include_router(inbox.router, prefix="/api")
app.include_router(settings_router.router, prefix="/api")
app.include_router(health.router, prefix="/api")
app.include_router(sse_router, prefix="/api")
app.include_router(members.router, prefix="/api")
app.include_router(media.router, prefix="/api")
app.include_router(restaurants.router, prefix="/api")
