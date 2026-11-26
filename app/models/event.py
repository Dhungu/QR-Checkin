from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin, UTCDateTime, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.attendee import Attendee


class Event(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "events"
    __table_args__ = (CheckConstraint("end_time > start_time", name="end_after_start"),)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    start_time: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    end_time: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)

    attendees: Mapped[list[Attendee]] = relationship(
        back_populates="event", cascade="all, delete-orphan", passive_deletes=True
    )
