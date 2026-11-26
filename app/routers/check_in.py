from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.security import checkin_limiter, require_staff
from app.routers.deps import SessionDep
from app.schemas import check_in as s
from app.services import qr
from app.services.check_in import AttendeeSnapshot, CheckInResult, Outcome, process_check_in

router = APIRouter(
    prefix="/api/v1/check-in",
    tags=["check-in"],
    dependencies=[Depends(require_staff), Depends(checkin_limiter)],
)

_RESPONSES = {
    200: {"model": s.CheckInSuccess},
    403: {"model": s.TicketRevoked | s.OutsideEventWindow, "description": "Revoked ticket or outside event window"},
    404: {"model": s.InvalidTicket},
    409: {"model": s.AlreadyCheckedIn},
}


def _brief(a: AttendeeSnapshot) -> s.AttendeeBrief:
    return s.AttendeeBrief(id=a.id, full_name=a.full_name, email=a.email, event_id=a.event_id, event_name=a.event_name)


def to_response(r: CheckInResult) -> JSONResponse:
    match r.outcome:
        case Outcome.SUCCESS:
            body, code = s.CheckInSuccess(attendee=_brief(r.attendee), timestamp=r.checked_in_at), 200
        case Outcome.ALREADY_CHECKED_IN:
            body = s.AlreadyCheckedIn(
                checked_in_at=r.checked_in_at, scanned_by=r.scanned_by, attendee=_brief(r.attendee)
            )
            code = 409
        case Outcome.TICKET_REVOKED:
            body, code = s.TicketRevoked(attendee=_brief(r.attendee)), 403
        case Outcome.OUTSIDE_EVENT_WINDOW:
            body = s.OutsideEventWindow(
                attendee=_brief(r.attendee), event_start=r.attendee.event_start, event_end=r.attendee.event_end
            )
            code = 403
        case _:
            body, code = s.InvalidTicket(), 404
    return JSONResponse(body.model_dump(mode="json"), status_code=code)


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.post("", responses=_RESPONSES)
async def check_in(payload: s.CheckInRequest, request: Request, session: SessionDep):
    """Validate a ticket and record attendance. Idempotent and safe under concurrent scans."""
    result = await process_check_in(
        session,
        ticket_token=payload.ticket_token.strip(),
        scanned_by=payload.scanned_by.strip(),
        device_info=payload.device_info or request.headers.get("user-agent", "")[:500],
        client_ip=_ip(request),
    )
    return to_response(result)


@router.post("/scan-image", responses={**_RESPONSES, 422: {"model": s.NoQrFound}})
async def scan_image(
    request: Request,
    session: SessionDep,
    file: Annotated[UploadFile, File(description="Photo or screenshot containing a QR code")],
    scanned_by: Annotated[str, Form(min_length=1, max_length=100)],
):
    """Decode a QR code from an uploaded image server-side, then check the ticket in."""
    limit = get_settings().max_upload_bytes
    raw = await file.read(limit + 1)
    if len(raw) > limit:
        return JSONResponse({"detail": "Image too large"}, status_code=413)
    token = qr.decode_qr(raw)
    if not token:
        return JSONResponse(s.NoQrFound().model_dump(), status_code=422)
    result = await process_check_in(
        session,
        ticket_token=token.strip(),
        scanned_by=scanned_by.strip(),
        device_info=request.headers.get("user-agent", "")[:500],
        client_ip=_ip(request),
    )
    return to_response(result)
