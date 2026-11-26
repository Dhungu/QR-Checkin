import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response

from app.core.security import require_admin
from app.routers.deps import SessionDep
from app.schemas.attendee import AttendeeRead
from app.services import events as svc
from app.services import qr

router = APIRouter(prefix="/api/v1/attendees", tags=["attendees"], dependencies=[Depends(require_admin)])


@router.get("/{attendee_id}/qr", responses={200: {"content": {"image/png": {}, "image/svg+xml": {}}}})
async def attendee_qr(
    attendee_id: uuid.UUID,
    session: SessionDep,
    format: Annotated[Literal["png", "svg"], Query()] = "png",
):
    """Rendered QR code for the attendee's ticket token."""
    attendee = await svc.get_attendee(session, attendee_id)
    headers = {"Cache-Control": "no-store"}
    if format == "svg":
        return Response(qr.render_qr_svg(attendee.ticket_token), media_type="image/svg+xml", headers=headers)
    return Response(qr.render_qr_png(attendee.ticket_token), media_type="image/png", headers=headers)


@router.post("/{attendee_id}/revoke", response_model=AttendeeRead)
async def revoke(attendee_id: uuid.UUID, session: SessionDep):
    """Invalidate a ticket (lost / refunded / fraudulent). Idempotent."""
    return await svc.revoke_attendee(session, attendee_id)
