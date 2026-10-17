"""Sign-in, sign-out and current-user endpoints."""

from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from ..dependencies import get_current_user, get_db
from ..services import (
    ServiceError,
    authenticate,
    cleanup_expired_sessions,
    create_session,
    delete_session,
)
from ..templating import templates

router = APIRouter()


@router.get("/login")
def login_page(request: Request):
    if getattr(request.state, "user", None):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"user": None, "csrf_token": "", "error": None, "username": ""},
    )


@router.post("/login")
def login_submit(
    request: Request,
    username: str = Form(""),
    password: str = Form(""),
    db=Depends(get_db),
):
    try:
        user = authenticate(db, username, password)
    except ServiceError as exc:
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "user": None,
                "csrf_token": "",
                "error": exc.message,
                "username": username,
            },
            status_code=exc.status_code,
        )

    settings = request.app.state.settings
    cleanup_expired_sessions(db)
    token, _ = create_session(db, user["id"], settings.session_ttl_hours)

    response = RedirectResponse("/", status_code=303)
    response.set_cookie(
        key=settings.session_cookie,
        value=token,
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        samesite="lax",
        secure=settings.secure_cookies,
        path="/",
    )
    return response


@router.post("/logout")
def logout(
    request: Request,
    csrf_token: str = Form(""),
    db=Depends(get_db),
):
    expected = getattr(request.state, "csrf_token", "")
    if expected and not hmac.compare_digest(csrf_token, expected):
        raise HTTPException(
            status_code=403,
            detail={"code": "INVALID_CSRF", "message": "Invalid CSRF token."},
        )

    settings = request.app.state.settings
    delete_session(db, request.cookies.get(settings.session_cookie))
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(settings.session_cookie, path="/")
    return response


@router.get("/api/me")
def me(request: Request, user: dict = Depends(get_current_user)):
    return {"user": user, "csrf_token": request.state.csrf_token}
