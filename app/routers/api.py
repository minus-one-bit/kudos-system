"""JSON API used by the dashboard."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ..dependencies import get_current_user, get_db, require_csrf
from ..schemas import KudosCreate
from ..services import create_kudos, list_feed, list_users

router = APIRouter(prefix="/api", tags=["kudos"])


@router.get("/users")
def colleagues(
    request: Request,
    q: str | None = None,
    user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    settings = request.app.state.settings
    return {"items": list_users(db, user["id"], q, limit=settings.users_max_results)}


@router.get("/kudos")
def feed(
    request: Request,
    limit: int = 20,
    offset: int = 0,
    user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    settings = request.app.state.settings
    limit = max(1, min(limit, settings.feed_max_page_size))
    offset = max(0, offset)
    items, total = list_feed(db, limit, offset)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.post("/kudos", status_code=201)
def give_kudos(
    payload: KudosCreate,
    request: Request,
    user: dict = Depends(require_csrf),
    db=Depends(get_db),
):
    return create_kudos(
        db,
        user,
        payload.recipient_id,
        payload.message,
        request.app.state.settings,
    )
