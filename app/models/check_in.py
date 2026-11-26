from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UTCDateTime, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.attendee import Attendee


class CheckIn(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "check_ins"

    # unique=True is the DB-level backstop for idempotency: even if a code path
    # skips the row lock, a second check-in for the same attendee cannot commit.
    attendee_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("attendees.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )
    scanned_by: Mapped[str] = mapped_column(String(100), nullable=False)
    scanned_at: Mapped[datetime] = mapped_column(
        UTCDateTime, server_default=func.now(), nullable=False
    )
    device_info: Mapped[str | None] = mapped_column(Text, nullable=True)

    attendee: Mapped[Attendee] = relationship(back_populates="check_in")
