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
    # T3.11.24 — `tier` is what **I** said about them; `state` is what is true of
    # the pair. They differ exactly when I called someone close and they have
    # not called me back: the tier is stored, and the state says `close_pending`
    # rather than `close`, because one person does not get to decide they are
    # trusted by another.
    tier: str = "connection"
    state: str = "connection"
    model_config = ConfigDict(from_attributes=True)


class MyInviteOut(BaseModel):
    token: str
    created_at: datetime
    expires_at: datetime
    status: str
    accepted_by_display_name: str | None = None
