import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator


class UserCreate(BaseModel):
    email: str | None = None
    phone: str | None = None
    password: str
    display_name: str
    is_carrier: bool = False

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class UserLogin(BaseModel):
    email: str | None = None
    phone: str | None = None
    password: str


class UserOut(BaseModel):
    id: uuid.UUID
    email: str | None
    phone: str | None
    display_name: str
    is_carrier: bool
    nostr_pubkey: str | None
    business_activity_level: float | None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
