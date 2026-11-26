"""Create a demo event with attendees and print their ticket links.

    python -m scripts.seed_demo
"""

import asyncio
from datetime import datetime, timedelta, timezone

from app.core.config import get_settings
from app.core.database import SessionLocal, engine
from app.models import Base
from app.schemas.attendee import AttendeeCreate
from app.schemas.event import EventCreate
from app.services import events as svc

PEOPLE = [("Ada Lovelace", "ada@example.com"), ("Alan Turing", "alan@example.com"),
          ("Grace Hopper", "grace@example.com"), ("Linus Torvalds", "linus@example.com"),
          ("Margaret Hamilton", "margaret@example.com")]


async def main() -> None:
    settings = get_settings()
    if settings.auto_create_tables:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    now = datetime.now(timezone.utc)
    async with SessionLocal() as session:
        event = await svc.create_event(
            session,
            EventCreate(name="DevConf Demo", start_time=now - timedelta(hours=1), end_time=now + timedelta(hours=6)),
        )
        print(f"Event: {event.name} ({event.id})")
        for name, email in PEOPLE:
            a = await svc.create_attendee(session, event.id, AttendeeCreate(full_name=name, email=email))
            print(f"  {name:<18} {settings.base_url}/ticket/{a.ticket_token}")
    await engine.dispose()
    print(f"\nOrganizer key: {settings.admin_api_key}   Staff key: {settings.staff_api_key}")


if __name__ == "__main__":
    asyncio.run(main())
