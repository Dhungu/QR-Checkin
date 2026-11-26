from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.core.config import BASE_DIR, get_settings
from app.core.security import public_limiter
from app.routers.deps import SessionDep
from app.services import events as svc
from app.services import qr

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
router = APIRouter(include_in_schema=False)


def _page(request: Request, name: str, status: int = 200, **ctx):
    ctx.setdefault("app_name", get_settings().app_name)
    return templates.TemplateResponse(request, name, ctx, status_code=status)


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return _page(request, "home.html")


@router.get("/scanner", response_class=HTMLResponse)
async def scanner(request: Request):
    return _page(request, "scanner.html")


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    return _page(request, "dashboard.html")


@router.get("/ticket/{ticket_token}", response_class=HTMLResponse, dependencies=[Depends(public_limiter)])
async def ticket(request: Request, ticket_token: str, session: SessionDep):
    found = await svc.get_ticket(session, ticket_token)
    if not found:
        return _page(request, "error.html", 404, title="Ticket not found",
                     message="This ticket link is invalid or has been removed.")
    attendee, event = found
    return _page(request, "ticket.html", attendee=attendee, event=event)


@router.get("/ticket/{ticket_token}/qr.png", dependencies=[Depends(public_limiter)])
async def ticket_qr(ticket_token: str, session: SessionDep):
    if not await svc.get_ticket(session, ticket_token):
        return Response(status_code=404)
    return Response(
        qr.render_qr_png(ticket_token), media_type="image/png", headers={"Cache-Control": "private, max-age=3600"}
    )
