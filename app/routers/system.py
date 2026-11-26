from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text

from app.core.security import Role, require_staff
from app.routers.deps import SessionDep

router = APIRouter(tags=["system"])


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/health/ready")
async def ready(session: SessionDep):
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(503, "database unavailable") from None
    return {"status": "ready"}


@router.get("/api/v1/auth/whoami")
async def whoami(role: Role = Depends(require_staff)):
    """Lets the web UI validate an API key and learn its role."""
    return {"role": role}
