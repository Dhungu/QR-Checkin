import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class CheckInRequest(BaseModel):
    ticket_token: str = Field(min_length=1, max_length=512)
    scanned_by: str = Field(min_length=1, max_length=100)
    device_info: str | None = Field(default=None, max_length=500)


class AttendeeBrief(BaseModel):
    id: uuid.UUID
    full_name: str
    email: str
    event_id: uuid.UUID
    event_name: str


class CheckInSuccess(BaseModel):
    status: Literal["SUCCESS"] = "SUCCESS"
    attendee: AttendeeBrief
    timestamp: datetime


class AlreadyCheckedIn(BaseModel):
    status: Literal["ALREADY_CHECKED_IN"] = "ALREADY_CHECKED_IN"
    checked_in_at: datetime | None
    scanned_by: str | None = None
    attendee: AttendeeBrief | None = None


class InvalidTicket(BaseModel):
    status: Literal["INVALID_TICKET"] = "INVALID_TICKET"


class TicketRevoked(BaseModel):
    status: Literal["TICKET_REVOKED"] = "TICKET_REVOKED"
    attendee: AttendeeBrief


class OutsideEventWindow(BaseModel):
    status: Literal["OUTSIDE_EVENT_WINDOW"] = "OUTSIDE_EVENT_WINDOW"
    attendee: AttendeeBrief
    event_start: datetime
    event_end: datetime


class NoQrFound(BaseModel):
    status: Literal["NO_QR_FOUND"] = "NO_QR_FOUND"
