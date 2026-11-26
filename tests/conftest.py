import os
import tempfile
from datetime import UTC, datetime, timedelta

# Configure BEFORE importing the app (settings are read at import time).
_tmp = tempfile.mkdtemp(prefix="qrci-")
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{_tmp}/test.db")
os.environ["ENVIRONMENT"] = "test"
os.environ["AUTO_CREATE_TABLES"] = "false"
os.environ["RATE_LIMIT_PER_MINUTE"] = "5000"
os.environ["QR_HMAC_SECRET"] = "test-secret-test-secret-test-secret-123"
os.environ["ADMIN_API_KEY"] = "admin-key-for-tests-1234"
os.environ["STAFF_API_KEY"] = "staff-key-for-tests-1234"

import httpx  # noqa: E402
import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402

from app.core.database import engine  # noqa: E402
from app.core.security import checkin_limiter, public_limiter  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402

ADMIN = {"X-API-Key": "admin-key-for-tests-1234"}
STAFF = {"X-API-Key": "staff-key-for-tests-1234"}


@pytest_asyncio.fixture(autouse=True)
async def clean_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    checkin_limiter.reset()
    public_limiter.reset()
    yield
    # Each test runs on its own event loop; pooled async connections can't cross loops.
    await engine.dispose()


@pytest_asyncio.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def admin():
    return ADMIN


@pytest.fixture
def staff():
    return STAFF


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat()


async def make_event(client, *, start_offset=-1, end_offset=2, name="PyCon Test"):
    now = datetime.now(UTC)
    r = await client.post(
        "/api/v1/events",
        headers=ADMIN,
        json={"name": name, "start_time": iso(now + timedelta(hours=start_offset)),
              "end_time": iso(now + timedelta(hours=end_offset))},
    )
    assert r.status_code == 201, r.text
    return r.json()


async def make_attendee(client, event_id, name="Ada Lovelace", email="ada@example.com"):
    r = await client.post(f"/api/v1/events/{event_id}/attendees", headers=ADMIN,
                          json={"full_name": name, "email": email})
    assert r.status_code == 201, r.text
    return r.json()
