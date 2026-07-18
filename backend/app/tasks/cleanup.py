"""T_TEST.3 — nightly cleanup of Playwright e2e users.

Convention (see frontend/e2e/helpers.ts): all smoke-test users register with
`<prefix>-<ts>-<rand>@e2e.vimana.local`. The `.local` TLD is unresolvable so
these addresses never send real mail. This task prunes them + everything
cascading off them (trips, deals, messages, trust edges) older than 24 h.

Cascade order matters (FK constraints, no `ON DELETE CASCADE` in our schema):
messages/attachments → deals/events → trips → invites/connections →
verifications → user.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select

from app.core.database import SyncSessionLocal
from app.models.deal import (
    Attachment,
    Deal,
    DealEvent,
    DealParticipant,
    DealVaultMessage,
    Dispute,
    OperatorAccessGrant,
)
from app.models.marketplace import InquiryMessage, Order, Trip, TripInquiry
from app.models.social import Connection, InviteLink
from app.models.trust import TrustEdge
from app.models.user import User
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
            db.execute(delete(Order).where(Order.id.in_(deal_ids)))  # safe if none match

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
            delete(InviteLink).where(InviteLink.inviter_id.in_(user_ids))
        )

        # Finally — the users themselves.
        result = db.execute(delete(User).where(User.id.in_(user_ids)))
        deleted_count = result.rowcount or len(user_ids)
        db.commit()

    logger.info("cleanup_e2e_users deleted %d test users", deleted_count)
    return {"deleted": deleted_count}
