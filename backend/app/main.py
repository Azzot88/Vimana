import logging
import os
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse

from app.api.admin import router as admin_router
from app.api.airports import router as airports_router
from app.api.auth import router as auth_router
from app.api.categories import router as categories_router
from app.api.cities import router as cities_router
from app.api.dealvault import router as dealvault_router
from app.api.deals import router as deals_router
from app.api.inquiries import router as inquiries_router
from app.api.keypair import router as keypair_router
from app.api.social import router as social_router
from app.api.telegram import router as telegram_router
from app.api.nostr import router as nostr_router
from app.api.threshold import router as threshold_router
from app.api.trips import router as trips_router
from app.api.trust import router as trust_router
from app.api.uba import router as uba_router
from app.api.verification import router as verification_router
from app.api.waitlist import router as waitlist_router
from app.core.database import AsyncSessionLocal
from app.core.logging_setup import configure_logging
from app.core.rate_limit import limiter
from app.core.superuser import ensure_user_zero

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        async with AsyncSessionLocal() as db:
            await ensure_user_zero(db)
    except Exception:
        logger.exception("User Zero promotion failed on startup")
    yield


app = FastAPI(title="Vimana", lifespan=lifespan)
app.state.limiter = limiter

origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]
# CORS spec: cannot combine `*` with credentials
allow_credentials = origins != ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(SlowAPIMiddleware)


@app.middleware("http")
async def _request_id_middleware(request: Request, call_next):
    request.state.request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    return response


def _req_id(request: Request) -> str:
    return getattr(request.state, "request_id", "")


@app.exception_handler(RateLimitExceeded)
async def _rate_limit_handler(request: Request, exc):
    return JSONResponse(
        status_code=429,
        content={
            "error": {
                "code": "rate_limited",
                "message": "Too many requests. Please slow down.",
                "request_id": _req_id(request),
            }
        },
    )


@app.exception_handler(StarletteHTTPException)
async def _http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "request_id": _req_id(request),
        },
        headers=getattr(exc, "headers", None) or {},
    )


@app.exception_handler(RequestValidationError)
async def _validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content=jsonable_encoder({
            "detail": exc.errors(),
            "request_id": _req_id(request),
        }),
    )


@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception):
    rid = _req_id(request)
    logger.exception(
        "Unhandled exception on %s %s (request_id=%s)",
        request.method, request.url.path, rid,
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "internal_error",
                "message": "Internal server error",
                "request_id": rid,
            }
        },
    )


app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(keypair_router, prefix="/api", tags=["keypair"])
app.include_router(social_router, prefix="/api", tags=["social"])
app.include_router(trips_router, prefix="/api/trips", tags=["trips"])
app.include_router(deals_router, prefix="/api/deals", tags=["deals"])
app.include_router(dealvault_router, prefix="/api/deals", tags=["dealvault"])
app.include_router(threshold_router, prefix="/api/threshold", tags=["threshold"])
app.include_router(nostr_router, prefix="/api/nostr", tags=["nostr"])
app.include_router(uba_router, prefix="/api", tags=["uba"])
app.include_router(telegram_router, prefix="/api/telegram", tags=["telegram"])
app.include_router(airports_router, prefix="/api/airports", tags=["airports"])
app.include_router(categories_router, prefix="/api/categories", tags=["categories"])
app.include_router(cities_router, prefix="/api/cities", tags=["cities"])
app.include_router(verification_router, prefix="/api", tags=["verification"])
app.include_router(trust_router, prefix="/api", tags=["trust"])
app.include_router(waitlist_router, prefix="/api/waitlist", tags=["waitlist"])
app.include_router(admin_router, prefix="/api", tags=["admin"])
app.include_router(inquiries_router, prefix="/api", tags=["inquiries"])


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/health/storage")
async def health_storage():
    from app.core.storage import check_storage
    result = check_storage()
    status_code = 200 if result.get("reachable") else 503
    return JSONResponse(status_code=status_code, content=result)
