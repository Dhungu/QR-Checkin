import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UTCDateTime, UUIDPrimaryKeyMixin


class AuditLog(UUIDPrimaryKeyMixin, Base):
    """Append-only record of every check-in attempt, including rejected ones."""

    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_logs_event_created", "event_id", "created_at"),)

    outcome: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    event_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("events.id", ondelete="SET NULL"), nullable=True
    )
    attendee_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("attendees.id", ondelete="SET NULL"), nullable=True
    )
    scanned_by: Mapped[str] = mapped_column(String(100), nullable=False)
    token_hint: Mapped[str | None] = mapped_column(String(8), nullable=True)
    client_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    device_info: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, server_default=func.now(), nullable=False
    )
