import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.verification import VerificationRequestStatus, VerificationTargetRole


class VerificationRequestCreate(BaseModel):
    target_role: str  # 'sender' | 'carrier'


class VerificationRequestOut(BaseModel):
    id: uuid.UUID
    deal_id: uuid.UUID
    requested_by_id: uuid.UUID
    # Typed as enums (not bare `str`) so OpenAPI advertises the exact values —
    # `RequestStatus` / `TargetRole` in frontend/src/api/verification.ts are the
    # mirror of these. JSON stays identical: both are `str`-enums.
    target_role: VerificationTargetRole
    status: VerificationRequestStatus
    created_at: datetime
    resolved_at: datetime | None
    model_config = ConfigDict(from_attributes=True)


class VerificationRespondBody(BaseModel):
    action: str  # 'later_in_person' | 'declined' | 'declined_polite' | 'upload'


class VerificationBadgeOut(BaseModel):
    id: uuid.UUID
    subject_id: uuid.UUID
    level: str
    source: str
    verified_by_id: uuid.UUID | None
    in_deal_id: uuid.UUID | None
    verified_at: datetime
    expires_at: datetime | None
    revoked_at: datetime | None
    model_config = ConfigDict(from_attributes=True)


class VerificationEscalateBody(BaseModel):
    reason: str


class UserVerificationSummary(BaseModel):
    """Public verification summary — no document contents."""
    subject_id: uuid.UUID
    highest_level: str | None
    # T_TRUST.1 — when the badge behind `highest_level` was issued. None when
    # there is no level, or when the badge carrying it is no longer active. The
    # UI must not render the level without this date (`D-EVIDENCE-DECAYS`).
    highest_level_at: datetime | None = None
    active_counts: dict[str, int]  # {'auto': N, 'peer': M, 'kyc': K}
    badges: list[VerificationBadgeOut]
