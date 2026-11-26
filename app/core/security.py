"""Ticket tokens, API-key auth and rate limiting."""

import base64
import hashlib
import hmac
import re
import secrets
import time
from collections import defaultdict, deque
from collections.abc import Callable
from typing import Literal

from fastapi import Depends, HTTPException, Request
from fastapi.security import APIKeyHeader

from app.core.config import get_settings

# ---------------------------------------------------------------- ticket tokens
# Token = <32-char random nonce> "." <22-char truncated HMAC-SHA256 of the nonce>  (55 chars)
# The signature lets us reject forged / mistyped tokens without touching the database,
# while the nonce carries 192 bits of entropy so tokens cannot be guessed or enumerated.
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{32}\.[A-Za-z0-9_-]{22}$")


def _sign(nonce: str) -> str:
    key = get_settings().qr_hmac_secret.encode()
    mac = hmac.new(key, nonce.encode(), hashlib.sha256).digest()[:16]
    return base64.urlsafe_b64encode(mac).rstrip(b"=").decode()


def generate_ticket_token() -> str:
    nonce = secrets.token_urlsafe(24)  # 24 bytes -> 32 chars
    return f"{nonce}.{_sign(nonce)}"


def verify_ticket_token(token: str) -> bool:
    if not isinstance(token, str) or not _TOKEN_RE.fullmatch(token):
        return False
    nonce, signature = token.split(".")
    return hmac.compare_digest(signature.encode(), _sign(nonce).encode())


# ---------------------------------------------------------------- API key auth
Role = Literal["admin", "staff"]
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def _matches(provided: str, expected: str) -> bool:
    return hmac.compare_digest(provided.encode(), expected.encode())


def resolve_role(api_key: str | None) -> Role | None:
    if not api_key:
        return None
    s = get_settings()
    if _matches(api_key, s.admin_api_key):
        return "admin"
    if _matches(api_key, s.staff_api_key):
        return "staff"
    return None


async def require_staff(api_key: str | None = Depends(_api_key_header)) -> Role:
    """Gate staff or organizers."""
    role = resolve_role(api_key)
    if role is None:
        raise HTTPException(401, "Missing or invalid API key", headers={"WWW-Authenticate": "ApiKey"})
    return role


async def require_admin(api_key: str | None = Depends(_api_key_header)) -> Role:
    """Organizers only."""
    role = resolve_role(api_key)
    if role is None:
        raise HTTPException(401, "Missing or invalid API key", headers={"WWW-Authenticate": "ApiKey"})
    if role != "admin":
        raise HTTPException(403, "Organizer key required")
    return role


# ---------------------------------------------------------------- rate limiting
class RateLimiter:
    """Per-client sliding window (in-process). Use Redis if you run several workers."""

    def __init__(self, scope: str, limit: Callable[[], int]):
        self.scope = scope
        self.limit = limit
        self.hits: dict[str, deque[float]] = defaultdict(deque)

    async def __call__(self, request: Request) -> None:
        client = request.client.host if request.client else "unknown"
        key = f"{self.scope}:{client}"
        now = time.monotonic()
        window = self.hits[key]
        while window and window[0] < now - 60:
            window.popleft()
        if len(window) >= self.limit():
            retry = int(60 - (now - window[0])) + 1
            raise HTTPException(429, "Too many requests", headers={"Retry-After": str(retry)})
        window.append(now)

    def reset(self) -> None:
        self.hits.clear()


checkin_limiter = RateLimiter("checkin", lambda: get_settings().rate_limit_per_minute)
public_limiter = RateLimiter("public", lambda: get_settings().rate_limit_per_minute)
