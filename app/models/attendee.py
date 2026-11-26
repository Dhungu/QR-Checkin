from __future__ import annotations

import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.check_in import CheckIn
    from app.models.event import Event


class AttendeeStatus(str, enum.Enum):
    REGISTERED = "registered"
    CHECKED_IN = "checked_in"
    REVOKED = "revoked"


class Attendee(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "attendees"
    __table_args__ = (UniqueConstraint("event_id", "email", name="uq_attendees_event_email"),)

    event_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("events.id", ondelete="CASCADE"), index=True, nullable=False
    )
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    ticket_token: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    status: Mapped[AttendeeStatus] = mapped_column(
        Enum(AttendeeStatus, name="attendee_status", values_callable=lambda e: [m.value for m in e]),
        default=AttendeeStatus.REGISTERED,
        server_default=AttendeeStatus.REGISTERED.value,
        nullable=False,
    )

    event: Mapped[Event] = relationship(back_populates="attendees")
    check_in: Mapped[CheckIn | None] = relationship(
        back_populates="attendee", cascade="all, delete-orphan", passive_deletes=True, uselist=False
    )
