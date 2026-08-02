import uuid
from datetime import datetime
from typing import Literal

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


class EmailChangeBody(BaseModel):
    """T3.15 — request a move to a new address. The grant travels in the
    `X-Step-Up-Token` header, not here: it stays out of the request schema, so
    it cannot surface in an OpenAPI example or a logged body."""

    email: str

    @field_validator("email")
    @classmethod
    def email_shape(cls, v: str) -> str:
        from app.core.email_verification import is_valid_email, normalize_email

        if not is_valid_email(v):
            raise ValueError("Invalid email address")
        return normalize_email(v)


class PasswordChangeBody(BaseModel):
    """T3.15 — set or replace the account password.

    No `current_password` field. Presence is already proven by step-up, and by
    whichever method the account actually has — asking for the old password on
    top would lock out passwordless accounts all over again, which is the exact
    defect this task exists to fix.
    """

    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class UserUpdate(BaseModel):
    display_name: str | None = None
    phone: str | None = None
    # T3.18 — how much of this identity a stranger may see. Validated here
    # rather than trusted from the client: an unknown value would fall back to
    # `full` in `visible_to`, i.e. a typo in the UI would silently un-hide an
    # account that asked to be hidden.
    public_profile: Literal["full", "minimal", "hidden"] | None = None
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
    # T3.12 — visible to counterparties on purpose: an account whose identity
    # key is gone can no longer sign, and must not read as a live one.
    key_lost: bool = False
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
    # T3.15 — the address awaiting proof, so the UI can show what is pending
    # and offer to cancel. `None` when no change is in flight.
    pending_email: str | None = None
    # T3.15 — lets the profile say "set a password" instead of "change" it, and
    # nothing more: the hash itself never leaves the server.
    has_password: bool = False
    # T3.16 — drives the "you have N codes left" banner. A count, never the
    # codes: the platform cannot show them again and should not pretend it can.
    recovery_codes_remaining: int = 0
    # T3.18 — the owner's own view of their visibility setting.
    public_profile: str = "full"
    # T3.19 — the one bit that decides whether this account is still a
    # participant or has become a record. Here rather than only on the keypair
    # endpoint so the shell can answer "is anything different about this
    # session" without asking a second question on every page.
    key_lost: bool = False
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


# T3.16 — recovery codes.


class RecoveryCodesOut(BaseModel):
    """The one and only moment these strings leave the server."""

    codes: list[str]
    generated_at: datetime


class RecoveryConsumeBody(BaseModel):
    """`identifier` is an email or an npub (hex) — whichever the account has.
    Someone who lost their only device still knows one of them, and demanding
    the right *kind* at the worst possible moment is a poor trade."""

    identifier: str
    code: str


class RecoverySessionOut(BaseModel):
    """A way to bind a new authenticator, not a session.

    `scope` is echoed so the client can see what it holds; `step_up_tokens` are
    included because the accounts that need this route usually have no other
    proof left to offer.
    """

    access_token: str
    token_type: str = "bearer"
    scope: str
    codes_remaining: int
    step_up_tokens: dict[str, str]
