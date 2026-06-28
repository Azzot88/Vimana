import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.dealvault import router as dealvault_router
from app.api.deals import router as deals_router
from app.api.social import router as social_router
from app.api.trips import router as trips_router

app = FastAPI(title="Vimana")

origins = os.getenv("CORS_ORIGINS", "*").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(social_router, prefix="/api", tags=["social"])
app.include_router(trips_router, prefix="/api/trips", tags=["trips"])
app.include_router(deals_router, prefix="/api/deals", tags=["deals"])
app.include_router(dealvault_router, prefix="/api/deals", tags=["dealvault"])


@app.get("/health")
async def health():
    return {"status": "ok"}
