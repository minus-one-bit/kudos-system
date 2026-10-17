"""Server-rendered pages: dashboard, moderation view, health check."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse

from ..dependencies import get_db, require_form_csrf
from ..services import (
    ServiceError,
    create_kudos,
    list_feed,
    list_kudos_admin,
    list_users,
)
from ..templating import templates

router = APIRouter()


@router.get("/")
def dashboard(request: Request, db=Depends(get_db)):
    user = getattr(request.state, "user", None)
    if not user:
        return RedirectResponse("/login", status_code=303)

    settings = request.app.state.settings
    users = list_users(db, user["id"], limit=settings.users_max_results)
    kudos, total = list_feed(db, settings.feed_page_size, 0)

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "user": user,
            "csrf_token": request.state.csrf_token,
            "users": users,
            "kudos": kudos,
            "total": total,
            "page_size": settings.feed_page_size,
            "max_message_length": settings.max_message_length,
            "form_error": None,
            "form_recipient_id": None,
            "form_message": "",
        },
    )


@router.post("/kudos")
def submit_kudos_form(
    request: Request,
    recipient_id: int = Form(...),
    message: str = Form(""),
    user: dict = Depends(require_form_csrf),
    db=Depends(get_db),
):
    """No-JavaScript fallback for the composer (Post/Redirect/Get)."""
    settings = request.app.state.settings
    try:
        create_kudos(db, user, recipient_id, message, settings)
    except ServiceError as exc:
        users = list_users(db, user["id"], limit=settings.users_max_results)
        kudos, total = list_feed(db, settings.feed_page_size, 0)
        return templates.TemplateResponse(
            request=request,
            name="dashboard.html",
            context={
                "user": user,
                "csrf_token": request.state.csrf_token,
                "users": users,
                "kudos": kudos,
                "total": total,
                "page_size": settings.feed_page_size,
                "max_message_length": settings.max_message_length,
                "form_error": exc.message,
                "form_recipient_id": recipient_id,
                "form_message": message,
            },
            status_code=exc.status_code,
        )
    return RedirectResponse("/", status_code=303)


@router.get("/admin")
def admin_page(request: Request, db=Depends(get_db)):
    user = getattr(request.state, "user", None)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if user["role"] != "admin":
        return templates.TemplateResponse(
            request=request,
            name="error.html",
            context={
                "user": user,
                "csrf_token": request.state.csrf_token,
                "status_code": 403,
                "message": "Administrator access is required to view this page.",
            },
            status_code=403,
        )

    kudos, total = list_kudos_admin(db, limit=50, offset=0, include_deleted=True)
    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={
            "user": user,
            "csrf_token": request.state.csrf_token,
            "kudos": kudos,
            "total": total,
        },
    )


@router.get("/healthz")
def healthz():
    return {"status": "ok"}
