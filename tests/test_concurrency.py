"""The headline guarantee: N simultaneous scans of one ticket admit exactly one."""

import asyncio
from collections import Counter

from sqlalchemy import func, select

from app.core.database import SessionLocal
from app.models import Attendee, AttendeeStatus, CheckIn
from tests.conftest import STAFF, make_attendee, make_event

N = 50


async def test_concurrent_scans_admit_exactly_one(client):
    ev = await make_event(client)
    att = await make_attendee(client, ev["id"])

    async def scan(i: int):
        return await client.post(
            "/api/v1/check-in", headers=STAFF, json={"ticket_token": att["ticket_token"], "scanned_by": f"gate-{i}"}
        )

    responses = await asyncio.gather(*(scan(i) for i in range(N)))
    outcomes = Counter(r.json()["status"] for r in responses)
    assert outcomes == {"SUCCESS": 1, "ALREADY_CHECKED_IN": N - 1}, outcomes
    assert Counter(r.status_code for r in responses) == {200: 1, 409: N - 1}

    # Every duplicate reports the same winner, and state is consistent.
    winner = next(r.json() for r in responses if r.status_code == 200)
    assert {r.json()["checked_in_at"] for r in responses if r.status_code == 409} == {winner["timestamp"]}
    async with SessionLocal() as s:
        assert await s.scalar(select(func.count()).select_from(CheckIn)) == 1
        assert await s.scalar(select(Attendee.status)) == AttendeeStatus.CHECKED_IN


async def test_concurrent_scans_of_different_tickets_all_succeed(client):
    ev = await make_event(client)
    atts = [await make_attendee(client, ev["id"], name=f"P{i}", email=f"p{i}@x.com") for i in range(20)]
    responses = await asyncio.gather(*(
        client.post("/api/v1/check-in", headers=STAFF, json={"ticket_token": a["ticket_token"], "scanned_by": "g"})
        for a in atts
    ))
    assert all(r.status_code == 200 for r in responses)
    stats = (await client.get(f"/api/v1/events/{ev['id']}/stats", headers=STAFF)).json()
    assert stats["checked_in"] == 20 and stats["pending"] == 0


async def test_unique_constraint_is_the_backstop(client):
    """Even if the row lock were bypassed, the DB refuses a second check-in row."""
    import pytest
    from sqlalchemy.exc import IntegrityError

    ev = await make_event(client)
    att = await make_attendee(client, ev["id"])
    async with SessionLocal() as s:
        s.add(CheckIn(attendee_id=__import__("uuid").UUID(att["id"]), scanned_by="a"))
        await s.commit()
        s.add(CheckIn(attendee_id=__import__("uuid").UUID(att["id"]), scanned_by="b"))
        with pytest.raises(IntegrityError):
            await s.commit()
