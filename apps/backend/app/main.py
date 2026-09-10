from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.database import init_indexes, close_db
from app.core.logging import setup_logging, CorrelationIdMiddleware, get_logger
from app.core.errors import AppError
from app.config import settings
from app.routers import (
    admin,
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
    email_templates,
    email_campaigns,
    reservego,
    reports,
)
from app.sse.campaign_stream import router as sse_router


# Defaults that are harmless locally and must never reach a deployed
# environment. Each fails *open*: an unset JWT secret signs every token with a
# constant published in this repo, and an unset webhook secret makes
# _verify_signature accept every unsigned request. Refusing to boot is the only
# way a misconfigured deploy becomes visible — otherwise it just runs, insecure
# and silent.
_INSECURE_DEFAULTS = {
    "jwt_secret": "change_me",
    "meta_webhook_verify_token": "verify_token",
}


def _assert_secure_config() -> None:
    """Raise unless the security-critical settings were actually configured."""
    if settings.environment == "development":
        return

    unsafe = [
        name
        for name, default in _INSECURE_DEFAULTS.items()
        if getattr(settings, name) == default
    ]
    if not settings.meta_webhook_secret:
        unsafe.append("meta_webhook_secret (unset)")

    if unsafe:
        raise RuntimeError(
            "Refusing to start with insecure configuration: "
            + ", ".join(unsafe)
            + ". Set these environment variables, or set ENVIRONMENT=development "
            "for local work."
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger = get_logger(__name__)
    _assert_secure_config()
    logger.info("backend_startup", version="1.0.0", status="loading_indexes")
    await init_indexes()
    logger.info("backend_startup_complete")
    yield
    await close_db()


app = FastAPI(
    title="DishPatch API",
    version="1.0.0",
    lifespan=lifespan,
    redirect_slashes=False, # trigger reload
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
        allow_origins=_origins,
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
async def global_exception_handler(request: Request, exc: Exception):
    # The response stays deliberately opaque, but the cause must not vanish:
    # without this an unhandled 500 left no trace anywhere, which is why the
    # ReserveGo upload failures could not be diagnosed at all.
    get_logger(__name__).exception(
        "unhandled_exception",
        path=request.url.path,
        method=request.method,
        error_type=type(exc).__name__,
        error=str(exc),
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "type": "server_error"},
    )


# Mount routers
app.include_router(auth.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
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
app.include_router(email_templates.router, prefix="/api")
app.include_router(email_campaigns.router, prefix="/api")
app.include_router(reservego.router, prefix="/api")
app.include_router(reports.router, prefix="/api")
