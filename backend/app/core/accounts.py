"""T3.28 pt.3b — bringing an account into existence, in one place.

There used to be two: `POST /auth/register` and the code path in `otp_verify`.
Two constructors for one thing is how accounts start differing by the door they
came through — one with a service keypair and a contact row, another without —
and every reader downstream then has to know which kind it is holding.

The endpoint is gone; this is what remains, and the tests build accounts
through it too, so the shape a test asserts on is the shape production makes.

Functions (PROJECT §6.2a):
- `create_user(db, ...)` — the only way an account is born.
  Called by: `api/auth.otp_verify`, `tests/conftest.make_account`.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.contacts import upsert_contact
from app.core.keypair import encrypt_nsec, generate_keypair
from app.core.security import hash_password
from app.models.user import User


async def create_user(
    db: AsyncSession,
    *,
    email: str | None = None,
    phone: str | None = None,
    password: str | None = None,
    display_name: str | None = None,
    locale: str = "en",
    can_carry: bool = True,
    can_send: bool = True,
    active_mode: str = "sender",
    verified: bool = False,
) -> User:
    """Create an account and its login contact. Flushes; does not commit.

    The service keypair is issued here rather than at any call site, because an
    account without one cannot be part of a threshold and cannot have its
    records signed — and that has been a source of repair migrations twice
    already (T3.12 backfilled twelve such accounts).

    `display_name` defaults to the local part of the address. It is a
    placeholder, not a guess at the person: the welcome screen replaces it, and
    `send_password_changed` refuses to greet anybody by it precisely because it
    is one.

    `verified` is passed, never inferred. Whether the address has been proven
    depends on how the account arrived — a code proves it, a form does not —
    and deciding that here would put the answer further from the evidence.
    """
    nsec_hex, npub_hex = generate_keypair()
    nsec_nonce, nsec_ct = encrypt_nsec(nsec_hex)

    identifier = email or phone or ""
    user = User(
        email=email,
        phone=phone,
        password_hash=hash_password(password) if password else None,
        display_name=(display_name or identifier.split("@")[0])[:100],
        locale=locale,
        can_carry=can_carry,
        can_send=can_send,
        active_mode=active_mode,
        nostr_pubkey=npub_hex,
        nsec_encrypted=nsec_ct,
        nsec_nonce=nsec_nonce,
        key_self_custody=False,
    )
    if email and verified:
        user.email_verified_at = datetime.now(timezone.utc)

    db.add(user)
    # `user.id` is assigned at flush, and the contact row references it.
    await db.flush()

    if email:
        contact = await upsert_contact(db, user, "email", email, verified=verified)
        if contact is not None:
            contact.is_login = True
    if phone:
        await upsert_contact(db, user, "sms", phone, verified=False)

    return user
