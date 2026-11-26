import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models import AttendeeStatus


class AttendeeCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)
    email: EmailStr


class AttendeeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_id: uuid.UUID
    full_name: str
    email: str
    ticket_token: str
    status: AttendeeStatus
    created_at: datetime


class AttendeePage(BaseModel):
    items: list[AttendeeRead]
    total: int
    limit: int
    offset: int


class ImportResult(BaseModel):
    created: int
    skipped: int
    errors: list[str]
