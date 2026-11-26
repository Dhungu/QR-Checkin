import uuid
from datetime import datetime

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class EventCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    slug: str | None = Field(default=None, max_length=100, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    start_time: AwareDatetime
    end_time: AwareDatetime

    @model_validator(mode="after")
    def _end_after_start(self) -> "EventCreate":
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


class EventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    start_time: datetime
    end_time: datetime
    created_at: datetime


class EventStats(BaseModel):
    event_id: uuid.UUID
    total: int
    checked_in: int
    pending: int
    revoked: int
    check_in_rate: float  # checked_in / (total - revoked), 0..1


class ActivityItem(BaseModel):
    attendee_id: uuid.UUID
    full_name: str
    email: str
    scanned_by: str
    scanned_at: datetime
