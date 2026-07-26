import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class UserCreate(BaseModel):
    """T3.11 — email + password only. `phone` is gone from the auth path
    entirely; it stays a profile contact field (see `UserUpdate`)."""

    email: str
    password: str
    display_name: str
    # T1.24: capability + initial mode. Everyone can both by default.
    can_carry: bool = True
    can_send: bool = True
    active_mode: str = "sender"

    @field_validator("email")
    @classmethod
    def email_shape(cls, v: str) -> str:
        from app.core.email_verification import is_valid_email, normalize_email

        if not is_valid_email(v):
            raise ValueError("Invalid email address")
        return normalize_email(v)

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v

    @field_validator("active_mode")
    @classmethod
    def active_mode_valid(cls, v: str) -> str:
        if v not in ("sender", "carrier"):
            raise ValueError("active_mode must be 'sender' or 'carrier'")
        return v


class UserLogin(BaseModel):
    """`login` is an email address. The field name is kept for wire
    compatibility; the phone branch is gone (T3.11)."""

    login: str
    password: str


class EmailVerifyBody(BaseModel):
    code: str


class UserUpdate(BaseModel):
    display_name: str | None = None
    phone: str | None = None
    notify_email: bool | None = None
    notify_telegram: bool | None = None
    notify_whatsapp: bool | None = None
    whatsapp_number: str | None = None
    # T1.24 mode switching + capability updates
    active_mode: str | None = None
    can_carry: bool | None = None
    can_send: bool | None = None
    # T1.26 receiving address (private, updated only via /me)
    receiving_country_iso: str | None = None
    receiving_city: str | None = None
    # int32 bound: Postgres INTEGER column — out-of-range dies in asyncpg as
    # an unhandled 500 (schemathesis finding, same as addresses.py).
    receiving_city_geoname_id: int | None = Field(default=None, ge=1, le=2_147_483_647)
    receiving_street: str | None = None
    receiving_postal_code: str | None = None
    receiving_note: str | None = None

    @field_validator("active_mode")
    @classmethod
    def active_mode_valid(cls, v: str | None) -> str | None:
        if v is not None and v not in ("sender", "carrier"):
            raise ValueError("active_mode must be 'sender' or 'carrier'")
        return v

    @field_validator("receiving_country_iso")
    @classmethod
    def country_iso_upper(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip().upper()
        if len(v) != 2:
            raise ValueError("receiving_country_iso must be ISO 3166-1 alpha-2 (2 chars)")
        return v


class UserOut(BaseModel):
    """Public user representation — DOES NOT include private fields.
    `receiving_*` fields never appear here; use `MeOut` for the owner's view.
    """
    id: uuid.UUID
    email: str | None
    phone: str | None
    display_name: str
    can_carry: bool = True
    can_send: bool = True
    active_mode: str = "sender"
    role: str = "user"
    nostr_pubkey: str | None
    business_activity_level: float | None
    # T3.1 — level slug derived from business_activity_level via core.uba.level_of.
    # Populated by view-layer callers; None for stale/unrecomputed users.
    uba_level: str | None = None
    notify_email: bool
    notify_telegram: bool
    notify_whatsapp: bool
    telegram_chat_id: str | None
    whatsapp_number: str | None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class MeOut(UserOut):
    """Owner-only view — includes private receiving address."""
    # T3.11 — drives the "confirm your email" banner and nothing else:
    # verification gates no endpoint. Derived from `User.email_verified_at`; an
    # account with no email reads False, and the banner skips it (nothing was
    # claimed, so nothing is pending).
    email_verified: bool = False
    receiving_country_iso: str | None = None
    receiving_city: str | None = None
    receiving_city_geoname_id: int | None = None
    receiving_street: str | None = None
    receiving_postal_code: str | None = None
    receiving_note: str | None = None
    # T_UX.4 B — presigned R2 URL, minted per response. None if not set.
    avatar_url: str | None = None


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
