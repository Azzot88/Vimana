import asyncio
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

from app.api.addresses import router as addresses_router
from app.api.admin import router as admin_router
from app.api.airports import router as airports_router
from app.api.auth import router as auth_router
from app.api.avatar import router as avatar_router
from app.api.categories import router as categories_router
from app.api.cities import router as cities_router
from app.api.dealvault import router as dealvault_router
from app.api.deals import router as deals_router
from app.api.inquiries import router as inquiries_router
from app.api.platform_params import router as platform_params_router
from app.api.cards import router as cards_router
from app.api.terms import router as terms_router
from app.api.keypair import router as keypair_router
from app.api.social import router as social_router
from app.api.telegram import router as telegram_router
from app.api.nostr import router as nostr_router
from app.api.nostr_auth import router as nostr_auth_router
from app.api.passkey import router as passkey_router
from app.api.step_up import router as step_up_router
from app.api.notices import router as notices_router
from app.api.participants import router as participants_router
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
    # T3.12 pt.1 — every account needs a service keypair. Separate try: a
    # failure here must not take down the app, and it must not mask the one
    # above.
    try:
        from app.core.service_keys import ensure_service_keys

        async with AsyncSessionLocal() as db:
            await ensure_service_keys(db)
    except Exception:
        logger.exception("Service key backfill failed on startup")
    # T3.11 — this setting hands out verified accounts without a mailbox. It
    # exists for the e2e suites and must be empty in production; say so loudly
    # rather than let a stray value ride along unnoticed.
    from app.core.email_verification import auto_verify_domains

    if auto_verify_domains():
        logger.warning(
            "E2E_AUTO_VERIFY_EMAIL_DOMAINS is set (%s) — registrations on these "
            "domains skip email verification. This must not be set in production.",
            ", ".join(sorted(auto_verify_domains())),
        )

    # T_OPS.1 — stop taking traffic before stopping. Installed last, so a
    # failure in any backfill above does not leave the drain half-wired, and
    # installed here rather than at import so it binds to the running loop —
    # with `--workers N` each worker installs its own.
    from app.core.readiness import install as install_drain

    install_drain(asyncio.get_running_loop())

    yield


# T_SEC.1 — Fail-safe default: docs are CLOSED unless EXPOSE_DOCS=true is
# explicitly set. Vimana runs a single-server topology (dev == prod), so an
# opt-in flag is safer than an opt-out one — a fresh deploy never accidentally
# exposes Swagger. To debug locally: put `EXPOSE_DOCS=true` in .env + rebuild.
_expose_docs = os.getenv("EXPOSE_DOCS", "false").strip().lower() in {"1", "true", "yes"}
app = FastAPI(
    title="Vimana",
    lifespan=lifespan,
    docs_url="/docs" if _expose_docs else None,
    redoc_url="/redoc" if _expose_docs else None,
    openapi_url="/openapi.json" if _expose_docs else None,
)
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


@app.middleware("http")
async def _reject_null_bytes(request: Request, call_next):
    """T_TEST.4 pt.2 — reject requests containing NUL bytes (`\\x00`) in
    query string or JSON body. Postgres UTF-8 columns reject NULs at driver
    level with a 500 (`CharacterNotInRepertoireError`); fail-fast at 400
    instead.

    Detects three forms:
      - raw `\\x00` byte in query string bytes or JSON body
      - URL-encoded `%00` in the query string (any case)
      - JSON-escaped `\\u0000` inside a string literal

    Multipart/form-data (file uploads) is skipped: binary payloads legitimately
    contain NUL bytes (photos, PDFs, etc.). The individual field validators
    on those endpoints already guard the text portions.
    """
    raw_query = request.scope.get("query_string", b"")
    if b"\x00" in raw_query or b"%00" in raw_query.lower():
        return JSONResponse(
            status_code=400,
            content={"detail": "NUL byte in query string"},
        )
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        # Only inspect textual JSON bodies; multipart/form + octet-stream may
        # carry binary that legitimately contains NUL.
        if content_type in ("application/json", "application/json; charset=utf-8", ""):
            body = await request.body()
            lower = body.lower()
            if b"\x00" in body or b"\\u0000" in lower:
                return JSONResponse(
                    status_code=400,
                    content={"detail": "NUL byte in request body"},
                )

            # Re-inject the body so downstream handlers can read it again.
            async def receive():
                return {"type": "http.request", "body": body, "more_body": False}

            request._receive = receive
    return await call_next(request)


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
app.include_router(addresses_router, prefix="/api", tags=["addresses"])
app.include_router(avatar_router, prefix="/api", tags=["avatar"])
app.include_router(keypair_router, prefix="/api", tags=["keypair"])
app.include_router(social_router, prefix="/api", tags=["social"])
app.include_router(trips_router, prefix="/api/trips", tags=["trips"])
app.include_router(deals_router, prefix="/api/deals", tags=["deals"])
app.include_router(dealvault_router, prefix="/api/deals", tags=["dealvault"])
app.include_router(threshold_router, prefix="/api/threshold", tags=["threshold"])
app.include_router(nostr_router, prefix="/api/nostr", tags=["nostr"])
# T3.13 — sits under /api/auth, not /api/nostr: this is a way to sign in, and
# nginx rate-limits the auth surface as a whole.
app.include_router(nostr_auth_router, prefix="/api/auth/nostr", tags=["auth"])
app.include_router(passkey_router, prefix="/api/auth/passkey", tags=["auth"])
app.include_router(step_up_router, prefix="/api/auth/step-up", tags=["auth"])
app.include_router(participants_router, prefix="/api", tags=["participants"])
app.include_router(notices_router, prefix="/api", tags=["notices"])
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
app.include_router(platform_params_router, prefix="/api", tags=["admin"])
app.include_router(terms_router, prefix="/api/deals", tags=["terms"])
app.include_router(cards_router, prefix="/api/deals", tags=["cards"])


@app.get("/health")
async def health():
    """Liveness: is this process alive. A supervisor restarts it when not.

    Deliberately **not** the same question as `/ready`. A process that is
    draining before shutdown is alive and must keep answering 200 here, or a
    supervisor would kill it mid-drain — which is the failure this pair exists
    to prevent, arriving from the other direction.
    """
    return {"status": "ok"}


@app.get("/ready")
async def ready():
    """T_OPS.1 — readiness: should this process be given traffic.

    503 while draining, so a balancer takes it out of rotation before it stops
    existing. With one backend and no health checking in front, this changes no
    routing **today** — it is the half of a zero-downtime deploy that has to be
    in place before a balancer can be put in front of several instances.

    Called by: an external load balancer or reverse proxy; `tests/test_readiness.py`.
    """
    from app.core.readiness import is_ready

    if is_ready():
        return {"status": "ready"}
    return JSONResponse(status_code=503, content={"status": "draining"})


@app.get("/health/storage")
async def health_storage():
    from app.core.storage import check_storage
    result = check_storage()
    status_code = 200 if result.get("reachable") else 503
    return JSONResponse(status_code=status_code, content=result)
