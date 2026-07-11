import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, index=True, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), unique=True, index=True, nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(100))
    # T1.24 dual role: capability flags (can this user do X?) + active UI mode.
    # Everyone can both carry and send by default — mode is a UI preference,
    # authorization is by capability. `active_mode` ∈ {'sender', 'carrier'}.
    can_carry: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    can_send: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    active_mode: Mapped[str] = mapped_column(String(10), default="sender", server_default="sender")
    nostr_pubkey: Mapped[str | None] = mapped_column(String(64), nullable=True)
    business_activity_level: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Notifications
    notify_email: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    notify_telegram: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    notify_whatsapp: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    telegram_chat_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    telegram_link_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    whatsapp_number: Mapped[str | None] = mapped_column(String(30), nullable=True)

    # Roles (T1.23). is_superuser = User Zero (nyxter@dealvault.club).
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    is_arbiter: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
