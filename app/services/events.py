"""Events, attendees, stats and CSV import."""

import csv
import io
import re
import secrets
import uuid

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import case, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import generate_ticket_token, verify_ticket_token
from app.models import Attendee, AttendeeStatus, CheckIn, Event
from app.schemas.attendee import AttendeeCreate, ImportResult
from app.schemas.event import ActivityItem, EventCreate, EventStats
from app.services.errors import BadRequest, Conflict, NotFound

MAX_IMPORT_ROWS = 5000
_email_adapter = TypeAdapter(EmailStr)


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:90] or "event"


# ------------------------------------------------------------------ events
async def create_event(session: AsyncSession, data: EventCreate) -> Event:
    slug = data.slug or slugify(data.name)
    if data.slug is None:
        taken = await session.scalar(select(Event.id).where(Event.slug == slug))
        if taken:
            slug = f"{slug}-{secrets.token_hex(2)}"
    event = Event(name=data.name.strip(), slug=slug, start_time=data.start_time, end_time=data.end_time)
    session.add(event)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise Conflict(f"Slug '{slug}' is already in use") from None
    return event


async def get_event(session: AsyncSession, event_id: uuid.UUID) -> Event:
    event = await session.get(Event, event_id)
    if event is None:
        raise NotFound("Event not found")
    return event


async def list_events(session: AsyncSession) -> list[Event]:
    return list((await session.scalars(select(Event).order_by(Event.start_time.desc()))).all())


async def event_stats(session: AsyncSession, event_id: uuid.UUID) -> EventStats:
    await get_event(session, event_id)

    def count_if(status: AttendeeStatus):
        return func.coalesce(func.sum(case((Attendee.status == status, 1), else_=0)), 0)

    row = (
        await session.execute(
            select(
                func.count(Attendee.id),
                count_if(AttendeeStatus.CHECKED_IN),
                count_if(AttendeeStatus.REGISTERED),
                count_if(AttendeeStatus.REVOKED),
            ).where(Attendee.event_id == event_id)
        )
    ).one()
    total, checked_in, pending, revoked = (int(x) for x in row)
    admissible = total - revoked
    return EventStats(
        event_id=event_id,
        total=total,
        checked_in=checked_in,
        pending=pending,
        revoked=revoked,
        check_in_rate=round(checked_in / admissible, 4) if admissible else 0.0,
    )


async def recent_activity(session: AsyncSession, event_id: uuid.UUID, limit: int = 15) -> list[ActivityItem]:
    await get_event(session, event_id)
    rows = (
        await session.execute(
            select(Attendee.id, Attendee.full_name, Attendee.email, CheckIn.scanned_by, CheckIn.scanned_at)
            .join(CheckIn, CheckIn.attendee_id == Attendee.id)
            .where(Attendee.event_id == event_id)
            .order_by(CheckIn.scanned_at.desc())
            .limit(limit)
        )
    ).all()
    return [
        ActivityItem(
            attendee_id=r.id, full_name=r.full_name, email=r.email, scanned_by=r.scanned_by, scanned_at=r.scanned_at
        )
        for r in rows
    ]


# --------------------------------------------------------------- attendees
async def create_attendee(session: AsyncSession, event_id: uuid.UUID, data: AttendeeCreate) -> Attendee:
    await get_event(session, event_id)
    attendee = Attendee(
        event_id=event_id,
        full_name=data.full_name.strip(),
        email=str(data.email).lower(),
        ticket_token=generate_ticket_token(),
    )
    session.add(attendee)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise Conflict("This email is already registered for the event") from None
    return attendee


async def get_attendee(session: AsyncSession, attendee_id: uuid.UUID) -> Attendee:
    attendee = await session.get(Attendee, attendee_id)
    if attendee is None:
        raise NotFound("Attendee not found")
    return attendee


async def list_attendees(
    session: AsyncSession, event_id: uuid.UUID, q: str | None, limit: int, offset: int
) -> tuple[list[Attendee], int]:
    await get_event(session, event_id)
    cond = [Attendee.event_id == event_id]
    if q:
        like = "%" + q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        cond.append(or_(Attendee.full_name.ilike(like, escape="\\"), Attendee.email.ilike(like, escape="\\")))
    total = await session.scalar(select(func.count(Attendee.id)).where(*cond)) or 0
    items = (
        await session.scalars(
            select(Attendee).where(*cond).order_by(Attendee.created_at.desc(), Attendee.id).limit(limit).offset(offset)
        )
    ).all()
    return list(items), total


async def revoke_attendee(session: AsyncSession, attendee_id: uuid.UUID) -> Attendee:
    attendee = await get_attendee(session, attendee_id)
    if attendee.status != AttendeeStatus.REVOKED:
        attendee.status = AttendeeStatus.REVOKED
        await session.commit()
    return attendee


async def get_ticket(session: AsyncSession, token: str) -> tuple[Attendee, Event] | None:
    """Look up a ticket by its public token (signature checked before the DB)."""
    if not verify_ticket_token(token):
        return None
    row = (
        await session.execute(
            select(Attendee, Event).join(Event, Event.id == Attendee.event_id).where(Attendee.ticket_token == token)
        )
    ).one_or_none()
    return (row[0], row[1]) if row else None


async def import_attendees_csv(session: AsyncSession, event_id: uuid.UUID, raw: bytes) -> ImportResult:
    await get_event(session, event_id)
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise BadRequest("CSV must be UTF-8 encoded") from None
    reader = csv.DictReader(io.StringIO(text))
    fields = {(f or "").strip().lower(): f for f in (reader.fieldnames or [])}
    name_col = fields.get("full_name") or fields.get("name")
    email_col = fields.get("email")
    if not name_col or not email_col:
        raise BadRequest("CSV needs a header row with 'full_name' (or 'name') and 'email' columns")

    existing = set((await session.scalars(select(Attendee.email).where(Attendee.event_id == event_id))).all())
    created, skipped, errors = 0, 0, []
    for line_no, row in enumerate(reader, start=2):
        if line_no - 1 > MAX_IMPORT_ROWS:
            raise BadRequest(f"Too many rows (max {MAX_IMPORT_ROWS})")
        name = (row.get(name_col) or "").strip()
        try:
            email = str(_email_adapter.validate_python((row.get(email_col) or "").strip())).lower()
        except ValidationError:
            errors.append(f"line {line_no}: invalid email")
            continue
        if not name or len(name) > 255:
            errors.append(f"line {line_no}: invalid name")
            continue
        if email in existing:
            skipped += 1
            continue
        existing.add(email)
        session.add(
            Attendee(event_id=event_id, full_name=name, email=email, ticket_token=generate_ticket_token())
        )
        created += 1
    try:
        await session.commit()
    except IntegrityError:  # concurrent import raced us on a duplicate email
        await session.rollback()
        raise Conflict("Import conflicted with concurrent registrations; please retry") from None
    return ImportResult(created=created, skipped=skipped, errors=errors[:20])
