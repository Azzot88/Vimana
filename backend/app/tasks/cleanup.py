"""T_TEST.3 — nightly cleanup of Playwright e2e users.

Convention (see frontend/e2e/helpers.ts): all smoke-test users register with
`<prefix>-<ts>-<rand>@e2e.vimana.local`. The `.local` TLD is unresolvable so
these addresses never send real mail. This task prunes them + everything
cascading off them (trips, deals, messages, trust edges) older than 24 h.

Cascade order matters (FK constraints, no `ON DELETE CASCADE` in our schema):
messages/attachments → deals/events → trips → notices/verifications/inquiries →
orders → invites/connections → user.

**This list is hand-maintained and has already drifted once.** `route_notes`
gained a `created_by` FK in T_UX.2 and nobody added it here, so the task blew up
on a `ForeignKeyViolation` the first time a pruned user had authored a note
(caught 2026-07-26). Every new FK to `users.id` has to be handled here — either
deleted with the user, or NULLed if the row is platform content the user merely
authored. The durable fix is `ON DELETE SET NULL`/`CASCADE` at the schema level
so the database enforces it instead of this function remembering to; that is a
migration across a dozen tables and is not attempted here.

One FK is deliberately left unhandled: `deal_events.actor_id` on a deal the
pruned user does not own. It is NOT NULL, so the only ways through are deleting
the event — which breaks that deal's hash chain (T3.6) — or rewriting who acted,
which is falsifying evidence. Neither is acceptable, so the task is allowed to
fail loudly on that case instead.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select, update

from app.core.database import AsyncSessionLocal, SyncSessionLocal
from app.models.deal import (
    Attachment,
    CardState,
    Deal,
    DealChainAnchor,
    DealEvent,
    DealEventType,
    DealParticipant,
    DealStatus,
    DealVaultMessage,
    Dispute,
    OperatorAccessGrant,
)
from app.models.marketplace import Chat, ChatMessage, Order, Trip
from app.models.notices import PlatformNotice, RouteNote
from app.models.social import Connection, InviteLink
from app.models.trust import TrustEdge
from app.models.user import User
from app.models.verification import (
    IdentityContainer,
    VerificationBadge,
    VerificationRequest,
)
from app.worker import celery_app

logger = logging.getLogger(__name__)

E2E_EMAIL_SUFFIX = "@e2e.vimana.local"
E2E_MAX_AGE_HOURS = 24


def _kept_emails() -> list[str]:
    """Addresses excluded from the sweep — see `Settings.E2E_KEEP_EMAILS`."""
    from app.core.config import settings

    raw = settings.E2E_KEEP_EMAILS or ""
    return [e.strip().lower() for e in raw.split(",") if e.strip()]


@celery_app.task(name="app.tasks.cleanup.cleanup_e2e_users")
def cleanup_e2e_users() -> dict:
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=E2E_MAX_AGE_HOURS)
    deleted_count = 0

    with SyncSessionLocal() as db:
        user_ids = [
            row[0]
            for row in db.execute(
                select(User.id).where(
                    User.email.like(f"%{E2E_EMAIL_SUFFIX}"),
                    User.created_at < cutoff,
                    # T_TEST.8 — the suite's long-lived sign-in account lives on
                    # this domain too. Deleting it is not cleanup, it is
                    # breaking tomorrow's run.
                    User.email.notin_(_kept_emails()),
                )
            ).all()
        ]
        if not user_ids:
            return {"deleted": 0}

        # Trips & their downstream. Delete deals + attachments + messages first.
        trip_ids = [
            row[0]
            for row in db.execute(
                select(Trip.id).where(Trip.carrier_id.in_(user_ids))
            ).all()
        ]
        deal_ids = [
            row[0]
            for row in db.execute(
                select(Deal.id).where(
                    (Deal.sender_id.in_(user_ids)) | (Deal.carrier_id.in_(user_ids))
                )
            ).all()
        ]

        if deal_ids:
            # Message-attachments → messages → deal events → grants → disputes → deals.
            msg_ids = [
                row[0]
                for row in db.execute(
                    select(DealVaultMessage.id).where(
                        DealVaultMessage.deal_id.in_(deal_ids)
                    )
                ).all()
            ]
            if msg_ids:
                db.execute(delete(Attachment).where(Attachment.message_id.in_(msg_ids)))
            db.execute(
                delete(DealVaultMessage).where(DealVaultMessage.deal_id.in_(deal_ids))
            )
            db.execute(delete(DealEvent).where(DealEvent.deal_id.in_(deal_ids)))
            # T3.6 — anchors FK to deals; drop them before the deal rows.
            db.execute(
                delete(DealChainAnchor).where(DealChainAnchor.deal_id.in_(deal_ids))
            )
            dispute_ids = [
                row[0]
                for row in db.execute(
                    select(Dispute.id).where(Dispute.deal_id.in_(deal_ids))
                ).all()
            ]
            if dispute_ids:
                db.execute(
                    delete(OperatorAccessGrant).where(
                        OperatorAccessGrant.dispute_id.in_(dispute_ids)
                    )
                )
                db.execute(delete(Dispute).where(Dispute.id.in_(dispute_ids)))
            db.execute(
                delete(DealParticipant).where(DealParticipant.deal_id.in_(deal_ids))
            )
            db.execute(delete(Deal).where(Deal.id.in_(deal_ids)))

        if trip_ids:
            # T3.11.23 — a deleted trip no longer takes a conversation with it.
            # There is no per-trip thread any more: the chat belongs to the two
            # people, and it outlives any one thing they talked about. Messages
            # that named the trip lose the reference and keep the words, which is
            # what a reader of their own history would expect.
            db.execute(
                update(ChatMessage)
                .where(ChatMessage.about_trip_id.in_(trip_ids))
                .values(about_trip_id=None)
            )
            db.execute(delete(Trip).where(Trip.id.in_(trip_ids)))

        # Rows the user *authored on platform content* — the content itself is
        # not theirs and must survive, so the reference is cleared rather than
        # the row deleted. `route_notes` is what actually broke this task:
        # T_UX.2 added the FK long after the cascade below was written.
        db.execute(
            update(RouteNote)
            .where(RouteNote.created_by.in_(user_ids))
            .values(created_by=None)
        )
        db.execute(
            update(PlatformNotice)
            .where(PlatformNotice.created_by.in_(user_ids))
            .values(created_by=None)
        )

        # Verification (T2.1): the container and badges are the user's own.
        # `verified_by_id` points at whoever vouched — clear it on badges that
        # belong to somebody else, they keep their badge.
        db.execute(
            update(VerificationBadge)
            .where(VerificationBadge.verified_by_id.in_(user_ids))
            .values(verified_by_id=None)
        )
        db.execute(
            delete(VerificationBadge).where(VerificationBadge.subject_id.in_(user_ids))
        )
        db.execute(
            delete(VerificationRequest).where(
                VerificationRequest.requested_by_id.in_(user_ids)
            )
        )
        db.execute(
            delete(IdentityContainer).where(IdentityContainer.owner_id.in_(user_ids))
        )

        # T3.11.23 — chats the user is in, and everything said in them. One row
        # per pair now, so this is the whole conversation with each of those
        # people rather than one thread per trip they once asked about.
        #
        # Messages first: the chat is their parent, and a chat deleted out from
        # under them leaves rows pointing at nothing.
        stray_chats = [
            row[0]
            for row in db.execute(
                select(Chat.id).where(
                    (Chat.user_low_id.in_(user_ids))
                    | (Chat.user_high_id.in_(user_ids))
                )
            ).all()
        ]
        if stray_chats:
            db.execute(
                delete(ChatMessage).where(ChatMessage.chat_id.in_(stray_chats))
            )
            db.execute(delete(Chat).where(Chat.id.in_(stray_chats)))
        db.execute(
            delete(ChatMessage).where(ChatMessage.sender_id.in_(user_ids))
        )

        # Participation in deals that are not theirs.
        db.execute(
            delete(DealParticipant).where(
                (DealParticipant.user_id.in_(user_ids))
                | (DealParticipant.invited_by.in_(user_ids))
            )
        )

        # Disputes on deals that are not theirs. The arbiter reference is
        # cleared (someone else's dispute keeps existing); one they opened
        # themselves goes, grants first.
        db.execute(
            update(Dispute)
            .where(Dispute.arbiter_id.in_(user_ids))
            .values(arbiter_id=None)
        )
        stray_disputes = [
            row[0]
            for row in db.execute(
                select(Dispute.id).where(Dispute.opened_by.in_(user_ids))
            ).all()
        ]
        if stray_disputes:
            db.execute(
                delete(OperatorAccessGrant).where(
                    OperatorAccessGrant.dispute_id.in_(stray_disputes)
                )
            )
            db.execute(delete(Dispute).where(Dispute.id.in_(stray_disputes)))
        db.execute(
            delete(OperatorAccessGrant).where(
                OperatorAccessGrant.granted_by.in_(user_ids)
            )
        )

        # Orders. The previous version matched `Order.id` against *deal* ids and
        # therefore never deleted anything; orders are reachable by sender.
        db.execute(delete(Order).where(Order.sender_id.in_(user_ids)))

        # Social + trust edges.
        db.execute(
            delete(TrustEdge).where(
                (TrustEdge.from_user_id.in_(user_ids))
                | (TrustEdge.to_user_id.in_(user_ids))
            )
        )
        db.execute(
            delete(Connection).where(
                (Connection.user_id.in_(user_ids))
                | (Connection.connected_user_id.in_(user_ids))
            )
        )
        db.execute(
            delete(InviteLink).where(
                (InviteLink.creator_id.in_(user_ids))
                | (InviteLink.used_by.in_(user_ids))
            )
        )

        # Finally — the users themselves.
        result = db.execute(delete(User).where(User.id.in_(user_ids)))
        deleted_count = result.rowcount or len(user_ids)
        db.commit()

    logger.info("cleanup_e2e_users deleted %d test users", deleted_count)
    return {"deleted": deleted_count}


@celery_app.task(name="app.tasks.cleanup.purge_old_sign_ins")
def purge_old_sign_ins() -> dict:
    """T_SEC.6 — forget devices nobody has used in `RETENTION_DAYS`.

    Sign-in history is a category of personal data the product did not hold
    before this task's feature existed, and a table that only grows is a
    liability that only grows with it. Ninety days is long enough that a laptop
    used on holiday is still recognised on the next holiday, and short enough
    that the table is a recent picture rather than a life story.

    Deleting a row means the device becomes new again, and the letter fires
    once more if it comes back. That is the intended reading: after three
    months of silence, "this is the same person's machine" is an assumption
    that has expired.

    Called by: celery beat (`worker.beat_schedule`), `tests/test_sign_ins.py`.
    """
    from app.models.sign_in import RETENTION_DAYS, UserSignIn

    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=RETENTION_DAYS)
    with SyncSessionLocal() as db:
        result = db.execute(
            delete(UserSignIn).where(UserSignIn.last_seen_at < cutoff)
        )
        db.commit()

    removed = result.rowcount or 0
    logger.info("purge_old_sign_ins removed %d rows", removed)
    return {"deleted": removed}


def _cancel_deadline_of(payload: dict | None) -> datetime | None:
    """The `expires_at` the server stamped on a `cancel.requested` card.

    Absent or unparsable means «no deadline», and the sweeper leaves the card
    alone: a request that cannot say when it stops waiting must not be closed by
    a guess about when it should have.
    """
    raw = (payload or {}).get("expires_at")
    if not isinstance(raw, str):
        return None
    try:
        moment = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


@celery_app.task(name="app.tasks.cleanup.close_stale_cancellations")
def close_stale_cancellations(limit: int = 200) -> dict:
    """T3.11.27 — a cancellation nobody answered goes through.

    Owner's rule, 2026-09-07: «Отмена до передачи должна подтверждаться обоими
    участниками… закроется по таймауту или по времени вылета». The deadline is
    stamped onto the card when it is raised (`api/cards._cancel_deadline`): the
    shorter of the two accounts' `cancel_timeout_hours`, capped by departure.
    Silence past it is the answer — otherwise a party who simply stops replying
    keeps the other one's cargo slot booked until the plane leaves.

    The card ends `expired`, not `accepted`: nobody accepted it. The deal ends
    `cancelled`, and the chain entry says `"by": "timeout"`, so a later reader
    can tell a cancellation both sides agreed to from one the clock decided.

    Called by: celery beat (`worker.beat_schedule`). Tests await
    `_close_stale_cancellations` directly — `asyncio.run` inside pytest-asyncio's
    running loop raises, and the bridge is not what they are checking.
    """
    return asyncio.run(_close_stale_cancellations(limit))


async def _close_stale_cancellations(limit: int) -> dict:
    # `AsyncSessionLocal` is deliberately the module-level import rather than a
    # local one: `tests/conftest.sync_sessions` rebinds it on this module so a
    # task run from a test talks to `vimana_test`. A local import would resolve
    # `app.core.database` at call time and reach past the patch into production
    # — the exact shape of the 2026-07-26 incident that fixture exists for.
    #
    # These three stay local: the worker has no reason to build the API's
    # dependency graph, and `api.cards` pulls in `api.deps`.
    from app.api.cards import record_card
    from app.core.cards import CANCELLABLE_STATUSES, CardKind
    from app.core.deal_chain import append_deal_event

    now = datetime.now(tz=timezone.utc)
    closed = 0
    async with AsyncSessionLocal() as db:
        cards = (
            await db.execute(
                select(DealVaultMessage)
                .where(
                    DealVaultMessage.card_kind == CardKind.cancel_requested.value,
                    DealVaultMessage.card_state == CardState.pending,
                )
                .order_by(DealVaultMessage.created_at)
                .limit(limit)
            )
        ).scalars().all()

        for card in cards:
            deadline = _cancel_deadline_of(card.card_payload)
            if deadline is None or deadline > now:
                continue
            deal = await db.get(Deal, card.deal_id)
            if deal is None:
                continue
            # `_emit` needs an actor and the chain has no «the platform did it».
            # A card with no author cannot be closed by the clock, so it is left
            # pending for a human answer rather than half-applied.
            requester = (
                await db.get(User, card.sender_id) if card.sender_id else None
            )
            if requester is None:
                continue

            card.card_state = CardState.expired
            # The deal moved on while the request sat there — a handover, a
            # dispute. The request lapses and nothing else happens: cancelling
            # a deal whose parcel is already flying would be the platform
            # rewriting an outcome it did not witness.
            if deal.status not in CANCELLABLE_STATUSES:
                await db.commit()
                continue

            await db.flush()
            await record_card(
                db,
                deal,
                CardKind.cancel_confirmed,
                requester,
                payload={"by": "timeout", "request_id": str(card.id)},
            )
            deal.status = DealStatus.cancelled
            await db.flush()
            await append_deal_event(
                db,
                deal_id=deal.id,
                event_type=DealEventType.cancelled,
                actor_id=requester.id,
                payload={
                    "card_kind": card.card_kind,
                    "message_id": str(card.id),
                    "by": "timeout",
                },
                author=requester,
            )
            await db.commit()
            closed += 1

    logger.info("close_stale_cancellations closed %d deals", closed)
    return {"closed": closed}
