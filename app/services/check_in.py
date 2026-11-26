"""Check-in business logic.

Concurrency model
-----------------
1. The attendee row is read with SELECT ... FOR UPDATE, so a second scan of the same
   ticket blocks until the first transaction finishes, then sees status=checked_in and
   returns ALREADY_CHECKED_IN. (SQLite: BEGIN IMMEDIATE serialises writers instead.)
2. `check_ins.attendee_id` is UNIQUE. If anything ever bypasses the lock, the losing
   INSERT raises IntegrityError and is turned into ALREADY_CHECKED_IN as well.
"""

import enum
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import verify_ticket_token
from app.models import Attendee, AttendeeStatus, AuditLog, CheckIn, Event

log = logging.getLogger(__name__)


class Outcome(str, enum.Enum):
    SUCCESS = "SUCCESS"
    ALREADY_CHECKED_IN = "ALREADY_CHECKED_IN"
    INVALID_TICKET = "INVALID_TICKET"
    TICKET_REVOKED = "TICKET_REVOKED"
    OUTSIDE_EVENT_WINDOW = "OUTSIDE_EVENT_WINDOW"


@dataclass(frozen=True)
class AttendeeSnapshot:
    """Plain copy of the fields we need, safe to use after the transaction ends."""

    id: uuid.UUID
    full_name: str
    email: str
    event_id: uuid.UUID
    event_name: str
    event_start: datetime
    event_end: datetime


@dataclass
class CheckInResult:
    outcome: Outcome
    attendee: AttendeeSnapshot | None = None
    checked_in_at: datetime | None = None
    scanned_by: str | None = None


async def _existing_check_in(session: AsyncSession, attendee_id: uuid.UUID):
    row = (
        await session.execute(
            select(CheckIn.scanned_at, CheckIn.scanned_by).where(CheckIn.attendee_id == attendee_id)
        )
    ).one_or_none()
    return (row.scanned_at, row.scanned_by) if row else (None, None)


async def _attempt(
    session: AsyncSession,
    ticket_token: str,
    scanned_by: str,
    device_info: str | None,
    now: datetime,
) -> CheckInResult:
    # Cheap rejection of forged tokens: no database round-trip needed.
    if not verify_ticket_token(ticket_token):
        return CheckInResult(Outcome.INVALID_TICKET)

    stmt = (
        select(Attendee, Event)
        .join(Event, Event.id == Attendee.event_id)
        .where(Attendee.ticket_token == ticket_token)
        .with_for_update(of=Attendee)
    )
    row = (await session.execute(stmt)).one_or_none()
    if row is None:
        await session.commit()
        return CheckInResult(Outcome.INVALID_TICKET)

    attendee, event = row
    snap = AttendeeSnapshot(
        id=attendee.id,
        full_name=attendee.full_name,
        email=attendee.email,
        event_id=event.id,
        event_name=event.name,
        event_start=event.start_time,
        event_end=event.end_time,
    )

    if attendee.status == AttendeeStatus.REVOKED:
        await session.commit()
        return CheckInResult(Outcome.TICKET_REVOKED, snap)

    if attendee.status == AttendeeStatus.CHECKED_IN:
        when, who = await _existing_check_in(session, attendee.id)
        await session.commit()
        return CheckInResult(Outcome.ALREADY_CHECKED_IN, snap, when, who)

    grace = timedelta(minutes=get_settings().checkin_grace_minutes)
    if not (event.start_time - grace <= now <= event.end_time + grace):
        await session.commit()
        return CheckInResult(Outcome.OUTSIDE_EVENT_WINDOW, snap)

    attendee.status = AttendeeStatus.CHECKED_IN
    session.add(CheckIn(attendee_id=attendee.id, scanned_by=scanned_by, scanned_at=now, device_info=device_info))
    try:
        await session.commit()
    except IntegrityError:
        # Lost a race the row lock should have prevented; the unique index caught it.
        await session.rollback()
        when, who = await _existing_check_in(session, snap.id)
        await session.commit()
        return CheckInResult(Outcome.ALREADY_CHECKED_IN, snap, when, who)

    return CheckInResult(Outcome.SUCCESS, snap, now, scanned_by)


async def _audit(
    session: AsyncSession,
    result: CheckInResult,
    ticket_token: str,
    scanned_by: str,
    device_info: str | None,
    client_ip: str | None,
) -> None:
    try:
        session.add(
            AuditLog(
                outcome=result.outcome.value,
                event_id=result.attendee.event_id if result.attendee else None,
                attendee_id=result.attendee.id if result.attendee else None,
                scanned_by=scanned_by,
                token_hint=ticket_token[:8],
                client_ip=client_ip,
                device_info=device_info,
            )
        )
        await session.commit()
    except Exception:  # noqa: BLE001 - never let audit failure change the gate decision
        await session.rollback()
        log.exception("audit log write failed")


async def process_check_in(
    session: AsyncSession,
    *,
    ticket_token: str,
    scanned_by: str,
    device_info: str | None = None,
    client_ip: str | None = None,
    now: datetime | None = None,
) -> CheckInResult:
    now = now or datetime.now(UTC)
    try:
        result = await _attempt(session, ticket_token, scanned_by, device_info, now)
    except Exception:
        await session.rollback()
        raise
    await _audit(session, result, ticket_token, scanned_by, device_info, client_ip)
    log.info(
        "check-in attempt",
        extra={"fields": {"outcome": result.outcome.value, "scanned_by": scanned_by}},
    )
    return result
