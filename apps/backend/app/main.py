from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.database import init_indexes, close_db
from app.core.logging import setup_logging, CorrelationIdMiddleware
from app.core.errors import AppError
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
)
from app.sse.campaign_stream import router as sse_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    await init_indexes()
    yield
    await close_db()


app = FastAPI(
    title="WhatsApp Bulk Sender API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(CorrelationIdMiddleware)


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
