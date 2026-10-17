"""Administrator-only moderation API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from ..dependencies import get_db, require_admin, require_admin_csrf
from ..schemas import ModerationRequest
from ..services import list_kudos_admin, moderate_kudos

router = APIRouter(prefix="/api/admin", tags=["moderation"])


@router.get("/kudos")
def list_all_kudos(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    include_deleted: bool = True,
    admin: dict = Depends(require_admin),
    db=Depends(get_db),
):
    items, total = list_kudos_admin(db, limit, offset, include_deleted)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.post("/kudos/{kudos_id}/hide")
def hide_kudos(
    kudos_id: int,
    payload: ModerationRequest,
    request: Request,
    admin: dict = Depends(require_admin_csrf),
    db=Depends(get_db),
):
    return moderate_kudos(
        db,
        kudos_id,
        admin,
        "hide",
        payload.reason,
        request.app.state.settings,
    )


@router.post("/kudos/{kudos_id}/unhide")
def unhide_kudos(
    kudos_id: int,
    payload: ModerationRequest,
    request: Request,
    admin: dict = Depends(require_admin_csrf),
    db=Depends(get_db),
):
    return moderate_kudos(
        db,
        kudos_id,
        admin,
        "unhide",
        payload.reason,
        request.app.state.settings,
    )


@router.delete("/kudos/{kudos_id}")
def delete_kudos(
    kudos_id: int,
    payload: ModerationRequest,
    request: Request,
    admin: dict = Depends(require_admin_csrf),
    db=Depends(get_db),
):
    return moderate_kudos(
        db,
        kudos_id,
        admin,
        "delete",
        payload.reason,
        request.app.state.settings,
    )
