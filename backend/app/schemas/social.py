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
    model_config = ConfigDict(from_attributes=True)


class MyInviteOut(BaseModel):
    token: str
    created_at: datetime
    expires_at: datetime
    status: str
    accepted_by_display_name: str | None = None
