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

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select, update

from app.core.database import SyncSessionLocal
from app.models.deal import (
    Attachment,
    Deal,
    DealChainAnchor,
    DealEvent,
    DealParticipant,
    DealVaultMessage,
    Dispute,
    OperatorAccessGrant,
)
from app.models.marketplace import InquiryMessage, Order, Trip, TripInquiry
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
            inquiry_ids = [
                row[0]
                for row in db.execute(
                    select(TripInquiry.id).where(TripInquiry.trip_id.in_(trip_ids))
                ).all()
            ]
            if inquiry_ids:
                db.execute(
                    delete(InquiryMessage).where(
                        InquiryMessage.inquiry_id.in_(inquiry_ids)
                    )
                )
                db.execute(
                    delete(TripInquiry).where(TripInquiry.id.in_(inquiry_ids))
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

        # Inquiries the user started on *other people's* trips (the trip-scoped
        # sweep above only covers their own).
        stray_inquiries = [
            row[0]
            for row in db.execute(
                select(TripInquiry.id).where(
                    (TripInquiry.sender_id.in_(user_ids))
                    | (TripInquiry.carrier_id.in_(user_ids))
                )
            ).all()
        ]
        if stray_inquiries:
            db.execute(
                delete(InquiryMessage).where(
                    InquiryMessage.inquiry_id.in_(stray_inquiries)
                )
            )
            db.execute(delete(TripInquiry).where(TripInquiry.id.in_(stray_inquiries)))
        db.execute(
            delete(InquiryMessage).where(InquiryMessage.sender_id.in_(user_ids))
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
