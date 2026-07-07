import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.responses import JSONResponse

from app.api.airports import router as airports_router
from app.api.auth import router as auth_router
from app.api.categories import router as categories_router
from app.api.dealvault import router as dealvault_router
from app.api.deals import router as deals_router
from app.api.social import router as social_router
from app.api.telegram import router as telegram_router
from app.api.trips import router as trips_router
from app.api.waitlist import router as waitlist_router
from app.core.rate_limit import limiter

app = FastAPI(title="Vimana")
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


@app.exception_handler(RateLimitExceeded)
async def _rate_limit_handler(request, exc):
    return JSONResponse(
        status_code=429,
        content={"detail": "Too many requests. Please slow down."},
    )


app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(social_router, prefix="/api", tags=["social"])
app.include_router(trips_router, prefix="/api/trips", tags=["trips"])
app.include_router(deals_router, prefix="/api/deals", tags=["deals"])
app.include_router(dealvault_router, prefix="/api/deals", tags=["dealvault"])
app.include_router(telegram_router, prefix="/api/telegram", tags=["telegram"])
app.include_router(airports_router, prefix="/api/airports", tags=["airports"])
app.include_router(categories_router, prefix="/api/categories", tags=["categories"])
app.include_router(waitlist_router, prefix="/api/waitlist", tags=["waitlist"])


@app.get("/health")
async def health():
    return {"status": "ok"}
