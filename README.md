# QR Event Check-In

![CI](https://github.com/Dhungu/qr-event-checkin/actions/workflows/ci.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.12-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-async-009688)
![Tests](https://img.shields.io/badge/tests-32%20passing-brightgreen)
![Coverage](https://img.shields.io/badge/coverage-83%25-green)

A production-style event check-in service. Organizers create events and issue **HMAC-signed QR tickets**;
gate staff scan them from a browser camera (or upload a photo) and get instant green/red feedback.
Every ticket admits **exactly one person, even if two staff scan it at the same instant.**

> Add screenshots to `docs/screenshots/` (organizer console, scanner, ticket pass) and link them here.

## Highlights

- **Race-safe, idempotent check-in**: `SELECT … FOR UPDATE` row lock + a `UNIQUE` constraint as a database-level backstop.
  Verified with a test that fires 50 simultaneous scans of one ticket on both SQLite and PostgreSQL.
- **Tamper-resistant tickets**: 192-bit random nonce + truncated HMAC-SHA256 signature, verified in constant time
  *before* any database lookup. Forged or mistyped codes never reach the DB.
- **Security hardening**: role-based API keys (organizer / staff), per-client rate limiting, append-only audit log of every
  attempt (including rejected ones), CSP and security headers, `Referrer-Policy: no-referrer` (ticket URLs carry a secret),
  tokens redacted from request logs, and a production config that refuses to start with default secrets.
- **Server-side + browser scanning**: `html5-qrcode` camera scanning, image upload decoded server-side with `pyzbar`
  (OpenCV fallback).
- **Polished UI**: organizer console with live stats, search, CSV import and activity feed; mobile-first scanner with
  sound, vibration and large status cards; boarding-pass style ticket page. Light/dark aware, keyboard accessible.
- **Engineering hygiene**: async SQLAlchemy 2.0, Alembic migrations (tested up/down on Postgres), Pydantic v2 schemas,
  structured JSON logs, health/readiness endpoints, Docker + Compose, GitHub Actions (lint + tests on SQLite *and* Postgres).

## Architecture

```mermaid
flowchart LR
    Org[Organizer console] -->|admin key| API
    Staff[Gate scanner<br/>camera / upload] -->|staff key| API
    Guest[Ticket page] -->|signed token in URL| API
    subgraph API[FastAPI]
      R[Routers] --> S[Services<br/>check-in, QR, events]
      S --> SEC[HMAC tokens · auth · rate limit]
    end
    S -->|SQLAlchemy async| DB[(PostgreSQL / SQLite)]
```

```
app/
  core/       config, async engine/session, HMAC tokens, auth, rate limiter, JSON logging
  models/     Event, Attendee, CheckIn, AuditLog
  schemas/    Pydantic v2 request/response models
  services/   check_in (locking logic), events (CRUD/stats/CSV), qr (render + decode)
  routers/    events, attendees, check_in, pages, system
templates/    Jinja2 pages (home, organizer, scanner, ticket)
static/       CSS, vanilla JS, vendored html5-qrcode
alembic/      migrations      tests/   pytest suite      scripts/   demo seed
```

## Quick start

**Docker (PostgreSQL):**
```bash
docker compose up --build
# open http://localhost:8000
```

**Local (SQLite):**
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt        # pyzbar also needs libzbar0 (apt install libzbar0 / brew install zbar)
cp .env.example .env
python -m scripts.seed_demo                # optional demo data + ticket links
uvicorn app.main:app --reload
```

Default dev keys are `dev-admin-key` (organizer) and `dev-staff-key` (gate staff). The web UI asks for the key on first use
and keeps it in the browser tab only. **Set real secrets for production** (`ENVIRONMENT=production` enforces this):
```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Camera access requires HTTPS or `localhost`.

## API

Interactive docs at `/docs`. Auth via `X-API-Key`.

| Method | Path | Role | Purpose |
|---|---|---|---|
| POST | `/api/v1/events` | admin | Create event |
| GET | `/api/v1/events`, `/{id}` | admin | List / fetch events |
| POST | `/api/v1/events/{id}/attendees` | admin | Register attendee, issue signed token |
| GET | `/api/v1/events/{id}/attendees?q=&limit=&offset=` | admin | Search / page attendees |
| POST | `/api/v1/events/{id}/attendees/import` | admin | Bulk CSV import (`full_name,email`) |
| GET | `/api/v1/attendees/{id}/qr?format=png\|svg` | admin | Rendered QR |
| POST | `/api/v1/attendees/{id}/revoke` | admin | Invalidate a ticket |
| POST | `/api/v1/check-in` | staff | Validate + record attendance |
| POST | `/api/v1/check-in/scan-image` | staff | Decode QR from an uploaded image, then check in |
| GET | `/api/v1/events/{id}/stats` | staff | Total / checked-in / pending / revoked |
| GET | `/api/v1/events/{id}/activity` | staff | Latest check-ins |
| GET | `/ticket/{token}` | public (token) | Mobile ticket pass |
| GET | `/health`, `/health/ready` | public | Liveness / DB readiness |

**Check-in responses**

| HTTP | `status` | Meaning |
|---|---|---|
| 200 | `SUCCESS` | Admitted; includes attendee and timestamp |
| 409 | `ALREADY_CHECKED_IN` | Duplicate; includes the *original* time and scanner |
| 404 | `INVALID_TICKET` | Unknown or forged token |
| 403 | `TICKET_REVOKED` | Ticket cancelled |
| 403 | `OUTSIDE_EVENT_WINDOW` | Before start / after end |
| 422 | `NO_QR_FOUND` | (scan-image) nothing decodable in the image |

Check-in is intentionally **idempotent rather than a toggle**: repeating a scan can never un-admit someone.

## How double entry is prevented

1. The attendee row is loaded with `SELECT … FOR UPDATE`. A concurrent scan of the same ticket blocks until the first
   transaction commits, then sees `checked_in` and returns `ALREADY_CHECKED_IN`.
2. `check_ins.attendee_id` is `UNIQUE`. If anything ever bypasses the lock, the losing `INSERT` raises `IntegrityError`,
   which is translated into the same duplicate response.
3. On SQLite (no row locks) every transaction starts with `BEGIN IMMEDIATE`, serialising writers.

`tests/test_concurrency.py` asserts that 50 parallel scans produce exactly one `SUCCESS`, 49 `ALREADY_CHECKED_IN`,
a single `check_ins` row, and that all duplicates report the same winning timestamp.

## Threat model

| Threat | Mitigation |
|---|---|
| Guessing / enumerating tickets | 192-bit random nonce, no sequential IDs |
| Forging tickets | HMAC-SHA256 signature, constant-time compare, checked before DB access |
| Sharing a screenshot of a ticket | One-time use; the second scan is rejected and logged with scanner + time |
| Brute-forcing the scan endpoint | Per-client rate limit (429 + `Retry-After`), audit log of invalid attempts |
| Staff key leakage | Separate staff/organizer keys; staff cannot create events or list attendees |
| Ticket URL leaking via `Referer` / logs | `Referrer-Policy: no-referrer`; token redacted from request logs; `no-store` caching |
| XSS in the web UI | Strict CSP (`script-src 'self'`), DOM built with `textContent`, no inline scripts |
| Misconfigured production | App refuses to start with default secrets/keys |

Known limits (good next steps): rate limiter state is in-process (use Redis behind multiple workers);
API keys are static (swap for per-staff JWT/OAuth); rotate `QR_HMAC_SECRET` invalidates all issued tickets.

## Development

```bash
make test        # pytest + coverage
make lint        # ruff
alembic revision --autogenerate -m "describe change"
# Run the suite against Postgres:
DATABASE_URL=postgresql+asyncpg://checkin:checkin@localhost:5432/checkin pytest
```

CI runs lint and the full suite on both SQLite and PostgreSQL, and exercises `alembic upgrade → check → downgrade`.

## License

MIT. Bundles [html5-qrcode](https://github.com/mebjas/html5-qrcode) (Apache-2.0) in `static/vendor/`.
