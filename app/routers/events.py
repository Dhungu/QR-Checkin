import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, UploadFile

from app.core.config import get_settings
from app.core.security import require_admin, require_staff
from app.routers.deps import SessionDep
from app.schemas.attendee import AttendeeCreate, AttendeePage, AttendeeRead, ImportResult
from app.schemas.event import ActivityItem, EventCreate, EventRead, EventStats
from app.services import events as svc
from app.services.errors import BadRequest

router = APIRouter(prefix="/api/v1/events", tags=["events"])


@router.post("", response_model=EventRead, status_code=201, dependencies=[Depends(require_admin)])
async def create_event(data: EventCreate, session: SessionDep):
    return await svc.create_event(session, data)


@router.get("", response_model=list[EventRead], dependencies=[Depends(require_admin)])
async def list_events(session: SessionDep):
    return await svc.list_events(session)


@router.get("/{event_id}", response_model=EventRead, dependencies=[Depends(require_admin)])
async def get_event(event_id: uuid.UUID, session: SessionDep):
    return await svc.get_event(session, event_id)


@router.get("/{event_id}/stats", response_model=EventStats, dependencies=[Depends(require_staff)])
async def stats(event_id: uuid.UUID, session: SessionDep):
    """Registered vs checked-in vs pending."""
    return await svc.event_stats(session, event_id)


@router.get("/{event_id}/activity", response_model=list[ActivityItem], dependencies=[Depends(require_staff)])
async def activity(event_id: uuid.UUID, session: SessionDep, limit: Annotated[int, Query(ge=1, le=100)] = 15):
    return await svc.recent_activity(session, event_id, limit)


@router.post(
    "/{event_id}/attendees", response_model=AttendeeRead, status_code=201, dependencies=[Depends(require_admin)]
)
async def register_attendee(event_id: uuid.UUID, data: AttendeeCreate, session: SessionDep):
    return await svc.create_attendee(session, event_id, data)


@router.get("/{event_id}/attendees", response_model=AttendeePage, dependencies=[Depends(require_admin)])
async def list_attendees(
    event_id: uuid.UUID,
    session: SessionDep,
    q: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    items, total = await svc.list_attendees(session, event_id, q, limit, offset)
    return AttendeePage(items=items, total=total, limit=limit, offset=offset)


@router.post(
    "/{event_id}/attendees/import", response_model=ImportResult, dependencies=[Depends(require_admin)]
)
async def import_attendees(event_id: uuid.UUID, session: SessionDep, file: Annotated[UploadFile, File()]):
    """Bulk-register attendees from a CSV with `full_name,email` columns."""
    raw = await file.read(get_settings().max_upload_bytes + 1)
    if len(raw) > get_settings().max_upload_bytes:
        raise BadRequest("File too large")
    return await svc.import_attendees_csv(session, event_id, raw)
