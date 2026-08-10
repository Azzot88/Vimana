"""T3.25 — normalising a contact and keeping `user_contacts` in step.

The normalisation is the part worth reading twice. `+971 50 123 45 67`,
`0501234567` and `971501234567` are one person and three strings, and a
`UNIQUE` constraint cannot tell. A phone number that has not been reduced to
one canonical form is not an identifier — it is a note. Everything downstream
(one confirmed contact per account, sign-in by phone, an invite addressed to a
number) rests on that reduction, so it happens once, here, at the door.

`phonenumbers` rather than a regular expression, and not as a preference:
national formats, trunk prefixes and country lengths are a moving dataset, and
the version of it we would hand-roll would be wrong for whichever country we
have not thought about. This is Google's libphonenumber, the same data the
phone in your pocket uses.

Functions (PROJECT §6.2a):
- `normalize(channel, raw)` — canonical form, or None if unusable.
  Called by: `is_valid`, `upsert_contact`, `schemas/user.UserUpdate`.
- `is_valid(channel, raw)` — shape check per channel.
  Called by: `schemas/user.UserUpdate`, T3.26 channel resolution.
- `upsert_contact(db, user, channel, value, verified)` — create or update the
  row for this (user, channel, value). Called by: `api/auth` on email
  confirmation, `api/telegram` on linking, `api/auth.update_me` on phone edit.
- `contacts_of(db, user_id)` — every contact of an account.
  Called by: tests today, T3.26 channel resolution next.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

import phonenumbers
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.email_verification import is_valid_email, normalize_email
from app.models.contact import CHANNELS, UserContact

logger = logging.getLogger(__name__)

PHONE_CHANNELS = ("sms", "whatsapp")


def normalize(channel: str, raw: str | None) -> str | None:
    """Canonical form for this channel, or None if the value cannot be used.

    None means "not usable as a contact", never "empty" — callers must not
    store the raw value as a fallback, because a value that failed to
    normalise is exactly the one that will not compare equal later.
    """
    if raw is None:
        return None
    value = raw.strip()
    if not value:
        return None

    if channel == "email":
        return normalize_email(value) if is_valid_email(value) else None

    if channel in PHONE_CHANNELS:
        try:
            # No default region: an international product cannot guess one, and
            # guessing wrong turns a Dubai number into a US number silently.
            # A number without `+` is therefore refused rather than assumed.
            parsed = phonenumbers.parse(value, None)
        except phonenumbers.NumberParseException:
            return None
        if not phonenumbers.is_valid_number(parsed):
            return None
        return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)

    if channel == "telegram":
        # A chat id, not a handle: it is what the Bot API answers to, and it is
        # already canonical. Digits only, possibly negative for groups.
        return value if value.lstrip("-").isdigit() else None

    return None


def is_valid(channel: str, raw: str | None) -> bool:
    return channel in CHANNELS and normalize(channel, raw) is not None


async def contacts_of(db: AsyncSession, user_id: uuid.UUID) -> list[UserContact]:
    result = await db.execute(
        select(UserContact).where(UserContact.user_id == user_id)
    )
    return list(result.scalars().all())


async def login_contact(db: AsyncSession, user_id: uuid.UUID) -> UserContact | None:
    """The confirmed contact this account signs in with, if it has one.

    Email first, then anything else: an address is the channel this product can
    actually reach today, and picking deterministically matters because a code
    is sent to whatever this returns — a function that answered differently on
    two calls would send the code one place and check it against another.

    Called by: `api/step_up.step_up_options`, `api/step_up._verify_contact_code`.
    """
    result = await db.execute(
        select(UserContact)
        .where(
            UserContact.user_id == user_id,
            UserContact.verified_at.isnot(None),
            UserContact.is_login.is_(True),
        )
        .order_by(UserContact.channel)
    )
    contacts = list(result.scalars().all())
    for contact in contacts:
        if contact.channel == "email":
            return contact
    return contacts[0] if contacts else None


async def _release_elsewhere(db: AsyncSession, user, channel: str, value: str) -> None:
    """Take a confirmed value away from any other account.

    Proof of control beats an older record, and this is the only rule that
    survives contact with reality: carriers recycle phone numbers, a Telegram
    chat belongs to whoever is holding the phone, and an email address can be
    handed over with a job. Somebody just proved they control this value; the
    account that proved it a year ago no longer does.

    Without this the partial unique index turns a normal life event into a
    permanent lockout — and it would surface as a 500 in a webhook, not as
    anything a person could act on.

    It removes a *contact*, never access: the other account keeps its session,
    its password and every other way in. **`T3.28` makes contacts sign-in
    identifiers, and at that point this needs a second look** — an account must
    not be able to lose its only way in because someone else got its old
    number. Recorded here rather than solved now, because the answer depends on
    what `is_login` ends up meaning.

    Called by: `upsert_contact`.
    """
    from sqlalchemy import delete

    await db.execute(
        delete(UserContact).where(
            UserContact.channel == channel,
            UserContact.value == value,
            UserContact.user_id != user.id,
            UserContact.verified_at.isnot(None),
        )
    )


async def upsert_contact(
    db: AsyncSession,
    user,
    channel: str,
    raw_value: str | None,
    *,
    verified: bool = False,
) -> UserContact | None:
    """Record a contact, or update the one already there.

    Does **not** commit — the caller owns the transaction, so a contact and the
    thing it belongs to (a confirmed address, a linked chat) land together or
    not at all.

    Marking verified is one-way here: a row already confirmed is not
    un-confirmed by a later unverified write of the same value. Losing a
    confirmation as a side effect of a profile save is not a thing a profile
    save should be able to do.
    """
    value = normalize(channel, raw_value)
    if value is None:
        # Silent by design — the schemas validate before anything reaches here,
        # so this is a programming error, not a user one — but not *traceless*:
        # a no-op returning None is exactly what made a test read the previous
        # owner's row and blame the wrong code (2026-08-09).
        logger.warning("contact not recorded: %r is not a usable %s", raw_value, channel)
        return None

    existing = (
        await db.execute(
            select(UserContact).where(
                UserContact.user_id == user.id,
                UserContact.channel == channel,
                UserContact.value == value,
            )
        )
    ).scalar_one_or_none()

    if existing:
        if verified and existing.verified_at is None:
            await _release_elsewhere(db, user, channel, value)
            existing.verified_at = datetime.now(timezone.utc)
        return existing

    if verified:
        await _release_elsewhere(db, user, channel, value)

    contact = UserContact(
        user_id=user.id,
        channel=channel,
        value=value,
        verified_at=datetime.now(timezone.utc) if verified else None,
    )
    db.add(contact)
    return contact
