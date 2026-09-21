"""T_UX.29 pt.7 — one place that says «кому-то это надо знать».

Owner, 2026-09-20: «Надо создать систему оповещений… Панель должна показывать
обновления, произошедшие за период неактивности. Если изменения произошли в
активном окне, их статусы показывать не нужно.»

Two deliveries and one write, in this order:

1. **The row** (`Notification`) — the durable answer to «что я пропустил». It
   survives a logout, a closed laptop and a week away, which is the whole thing
   a panel is for.
2. **The live nudge** — the same fact published to Redis, where whatever tabs
   this person has open are listening (`api.events.stream`). This is the second
   mechanism the owner asked for beside the ten-second beat: «лучше, когда на
   той стороне нажали кнопку… это передавалось другой стороне».

Redis rather than a direct call, because there are two uvicorn workers: the
person who pressed the button and the person waiting for it are, half the time,
talking to different processes. A publish is how one reaches the other, and it
is the same broker Celery, the rate limits and the token blacklist already use.

**The nudge is best-effort and the row is not.** Redis being down must not fail
a card that has already been written to the chain: the screen then learns on its
next beat, ten seconds later, which is exactly the behaviour we had before this
module existed. The row is written inside the caller's transaction, so a
notification about a card that was rolled back cannot exist.

Push is the third delivery and is deliberately not here yet — `PushSubscription`
collects endpoints, and this is the function that will fan out to them once there
are VAPID keys and a consent flow.

Functions (PROJECT §6.2a):
  - `notify(db, user_ids, kind, ...)` — write the rows and publish the nudge.
    Called by: `api.cards._raise_card`, `api.dealvault.post_message`,
    `api.deals.match`, `api.requests.create_request`.
  - `channel_for(user_id)` — the Redis channel a person's tabs listen on.
    Called by: `notify`, `api.events.stream`.
"""
from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification, NotificationKind

logger = logging.getLogger(__name__)


def channel_for(user_id: uuid.UUID | str) -> str:
    """One channel per person, not per deal.

    A tab subscribes once and hears about everything addressed to whoever is
    signed in, which is what the bell needs. Filtering to «is this my open
    deal» is the client's job and a cheap one — it already knows which deal it
    is showing, and the server would have to be told.
    """
    return f"vimana:events:{user_id}"


async def notify(
    db: AsyncSession,
    user_ids: Iterable[uuid.UUID | None],
    kind: NotificationKind,
    *,
    deal_id: uuid.UUID | None = None,
    trip_id: uuid.UUID | None = None,
    payload: dict | None = None,
    exclude: uuid.UUID | None = None,
) -> None:
    """Tell these people, once each, and nudge whatever they have open.

    `exclude` is the actor: nobody is notified of their own press. It is passed
    rather than inferred because half the callers act on somebody's behalf — a
    status the server moves has no human author at all.

    Duplicates are collapsed and `None`s dropped, so a caller may hand over
    `[deal.sender_id, deal.carrier_id, deal.recipient_id]` without first working
    out which of them exist and which is the same person twice. A sender who
    named themselves recipient is one row, not two.

    **Does not commit.** The rows join the caller's transaction, so a card that
    fails validation cannot leave a notification about itself behind.
    """
    targets: list[uuid.UUID] = []
    for candidate in user_ids:
        if candidate is None or candidate == exclude or candidate in targets:
            continue
        targets.append(candidate)
    if not targets:
        return

    for user_id in targets:
        db.add(
            Notification(
                user_id=user_id,
                kind=kind.value,
                deal_id=deal_id,
                trip_id=trip_id,
                payload=payload or None,
            )
        )

    await _publish(
        targets,
        {
            "kind": kind.value,
            "deal_id": str(deal_id) if deal_id else None,
            "trip_id": str(trip_id) if trip_id else None,
        },
    )


async def _publish(user_ids: list[uuid.UUID], event: dict) -> None:
    """The live half, and the half that is allowed to fail.

    Wrapped whole rather than per-recipient: the failure that matters is «Redis
    is unreachable», and it is the same failure for all of them. A log line at
    warning level, because a silent degradation from «instant» to «within ten
    seconds» is precisely the kind of thing that goes unnoticed for a month.
    """
    try:
        from app.core.redis_client import get_client

        client = get_client()
        body = json.dumps(event)
        for user_id in user_ids:
            await client.publish(channel_for(user_id), body)
    except Exception:  # noqa: BLE001 — the beat is the fallback, by design
        logger.warning("live event not published; the poll will carry it", exc_info=True)
