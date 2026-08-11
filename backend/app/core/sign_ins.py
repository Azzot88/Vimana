"""T_SEC.6 — notice when an account is entered from somewhere it has not been.

Since `T3.28` an account opens with a code sent to its mailbox and no password
at all. The mailbox became the key, and nothing watched it: a quiet sign-in
produced no record and no signal anywhere. A password change at least ends every
session, which the owner notices; a sign-in by code is invisible by design.

**The fingerprint is deliberately coarse** — browser family, OS family, and the
/24 the request came from. Not the `User-Agent` string: that changes with every
browser update, and a letter that arrives each time Chrome updates itself is a
letter nobody reads by the month it matters. Not the exact address either:
consumer addresses move within a carrier's range constantly, and the owner would
be told about themselves.

The cost of coarseness is stated rather than hidden: someone on the same /24
using the same browser and OS — a housemate, an office — does not raise the
letter. That is the trade this grain buys, and the alternative trade (a letter
a week) buys nothing, because it ends up in a folder.

Functions (PROJECT §6.2a):
- `describe(user_agent) -> str` — "Chrome on macOS" from a `User-Agent`.
  Called by: `record`, `tests/test_sign_ins.py`.
- `network_of(ip) -> str` — the /24 (or /48) an address belongs to.
  Called by: `record`, `tests/test_sign_ins.py`.
- `fingerprint(device, network) -> str` — sha256 of the pair.
  Called by: `record`, `tests/test_sign_ins.py`.
- `record(db, user_id, request) -> dict | None` — remembers this device and
  answers whether it had been seen. Called by: `announce`,
  `api/auth.consume_recovery_code`, `api/passkey.signup_verify`,
  `api/nostr_auth.nostr_signup`.
- `announce(db, user_id, request)` — records, and sends the letter if the
  device is new. Called by: `api/auth.otp_verify`, `api/auth.login`,
  `api/passkey.login_verify`, `api/nostr_auth.nostr_verify`.
"""
from __future__ import annotations

import hashlib
import ipaddress
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.client_ip import client_ip
from app.models.sign_in import UserSignIn

logger = logging.getLogger(__name__)


def describe(user_agent: str | None) -> str:
    """A short human label for the client that made the request.

    Parsed by `user-agents` rather than by hand. Agent strings are a moving
    heap of vendor tokens pretending to be each other — Chrome claims to be
    Safari, which claims to be Mozilla — and a regex written today is wrong by
    the next browser release. An unparseable or absent agent becomes
    "unknown device", which is a truthful thing to put in a letter.
    """
    raw = (user_agent or "").strip()
    if not raw:
        return "unknown device"

    from user_agents import parse

    parsed = parse(raw)
    browser = parsed.browser.family or "unknown browser"
    system = parsed.os.family or "unknown OS"
    return f"{browser} on {system}"[:120]


def network_of(ip: str) -> str:
    """The address's neighbourhood: /24 for IPv4, /48 for IPv6.

    A whole address changes as a phone moves between masts; the network it sits
    in mostly does not. This is also the only form of the address that is
    written down anywhere — see `models/sign_in`.
    """
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return "unknown"
    prefix = 24 if address.version == 4 else 48
    return str(ipaddress.ip_network(f"{ip}/{prefix}", strict=False))


def fingerprint(device: str, network: str) -> str:
    return hashlib.sha256(f"{device}|{network}".encode("utf-8")).hexdigest()


async def record(db, user_id, request) -> dict | None:
    """Remember this sign-in; return facts for the letter if it was a new one.

    Returns `None` when the device is already known — the caller sends nothing.
    Otherwise a dict of what the letter needs (`device`, `ip`, `when`), with the
    address passed along rather than stored: the geolocation lookup happens in
    the Celery task, and nothing keeps the full address afterwards.

    **Commits its own row.** The five call sites sit in five different
    transaction shapes — one of them (`login`) does not write at all — and a
    helper that silently depends on the caller committing is a helper that
    works in four places out of five.

    Never raises into a sign-in. Failing to write a history row must not be able
    to keep somebody out of their own account; a broken audit trail is a smaller
    problem than a door that will not open, and it is logged rather than
    swallowed.
    """
    try:
        ip = client_ip(request)
        device = describe(request.headers.get("User-Agent"))
        network = network_of(ip)
        digest = fingerprint(device, network)

        now = datetime.now(timezone.utc)
        known = (
            await db.execute(
                select(UserSignIn).where(
                    UserSignIn.user_id == user_id,
                    UserSignIn.fingerprint == digest,
                )
            )
        ).scalars().first()

        if known is not None:
            known.last_seen_at = now
            await db.commit()
            return None

        db.add(
            UserSignIn(
                user_id=user_id,
                fingerprint=digest,
                device=device,
                network=network,
                first_seen_at=now,
                last_seen_at=now,
            )
        )
        try:
            await db.commit()
        except IntegrityError:
            # Two sign-ins racing on the same new device. The unique index
            # decides; the loser reports nothing, because the winner is already
            # sending the letter and one event deserves one letter.
            await db.rollback()
            return None

        return {"device": device, "ip": ip, "when": now}
    except Exception:
        logger.exception("could not record sign-in for %s", user_id)
        # The session is handed back usable. A caller that commits after this
        # would otherwise inherit a failed transaction and turn a bookkeeping
        # miss into a 500 on the sign-in itself.
        try:
            await db.rollback()
        except Exception:
            pass
        return None


async def announce(db, user_id, request) -> None:
    """Record the sign-in and, if the device is new, send the letter.

    The two halves are separate functions because two of the seven entry points
    want only the first half. An account being *created* has no old device to
    contrast with — writing to somebody the moment they sign up to say their
    sign-up was unusual is nonsense. And `consume_recovery_code` already sends
    its own security letter at that instant; a second one arriving alongside it
    is the noise that trap 1 of this task is about.

    Fire-and-forget, like every other security letter here: a broker that is
    down must not turn into a sign-in that fails.
    """
    facts = await record(db, user_id, request)
    if facts is None:
        return

    from app.tasks.notifications import send_new_device

    try:
        send_new_device.delay(
            str(user_id),
            facts["device"],
            facts["ip"],
            # Formatted here rather than in the letter: the task is the wrong
            # place to decide how a timestamp reads, and `%Y-%m-%d %H:%M UTC`
            # is unambiguous in every locale the product speaks.
            facts["when"].strftime("%Y-%m-%d %H:%M UTC"),
        )
    except Exception:
        logger.exception("could not queue new-device letter for %s", user_id)
