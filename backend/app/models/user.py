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
    is_carrier: Mapped[bool] = mapped_column(Boolean, default=False)
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
