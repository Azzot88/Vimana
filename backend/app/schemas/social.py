import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.user import UserOut


class InviteLinkOut(BaseModel):
    id: uuid.UUID
    token: str
    expires_at: datetime
    used_by: uuid.UUID | None
    model_config = ConfigDict(from_attributes=True)


class ConnectionOut(BaseModel):
    id: uuid.UUID
    connected_user_id: uuid.UUID
    connected_user: UserOut
    created_at: datetime
    # T3.12.06 — what is true between us, from `close_pairs`: `connection`,
    # `close_pending` (I asked), `close_requested` (they asked me) or `close`.
    state: str = "connection"
    model_config = ConfigDict(from_attributes=True)


class ClosePairOut(BaseModel):
    """T3.12.06 — one close person, or one request between two people, from the
    caller's side. The other person by name only: closeness is what pt.2 opens
    the profile to, and this list must not open it first."""

    id: uuid.UUID
    user_id: uuid.UUID
    display_name: str | None
    handle: str | None
    #: `close` · `close_pending` · `close_requested` · `none` (declined/ended).
    state: str
    requested_at: datetime
    accepted_at: datetime | None


class MyInviteOut(BaseModel):
    token: str
    created_at: datetime
    expires_at: datetime
    status: str
    accepted_by_display_name: str | None = None
