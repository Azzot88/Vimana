import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class VerificationRequestCreate(BaseModel):
    target_role: str  # 'sender' | 'carrier'


class VerificationRequestOut(BaseModel):
    id: uuid.UUID
    deal_id: uuid.UUID
    requested_by_id: uuid.UUID
    target_role: str
    status: str
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
    active_counts: dict[str, int]  # {'auto': N, 'peer': M, 'kyc': K}
    badges: list[VerificationBadgeOut]
