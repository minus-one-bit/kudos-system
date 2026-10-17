"""Shared FastAPI dependencies: database, authentication, authorization, CSRF."""

from __future__ import annotations

import hmac
import sqlite3
from typing import Iterator

from fastapi import Depends, Form, HTTPException, Request

from .db import connect


def get_db(request: Request) -> Iterator[sqlite3.Connection]:
    """One connection per request, always closed."""
    connection = connect(request.app.state.db_path)
    try:
        yield connection
    finally:
        connection.close()


def get_current_user(request: Request) -> dict:
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(
            status_code=401,
            detail={"code": "UNAUTHENTICATED", "message": "Sign in required."},
        )
    return user


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(
            status_code=403,
            detail={
                "code": "FORBIDDEN",
                "message": "Administrator access required.",
            },
        )
    return user


def _check_csrf(request: Request) -> None:
    expected = getattr(request.state, "csrf_token", "")
    supplied = request.headers.get("X-CSRF-Token", "")
    if not expected or not supplied or not hmac.compare_digest(supplied, expected):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "INVALID_CSRF",
                "message": "Invalid or missing CSRF token.",
            },
        )


def require_csrf(
    request: Request, user: dict = Depends(get_current_user)
) -> dict:
    _check_csrf(request)
    return user


def require_admin_csrf(
    request: Request, user: dict = Depends(require_admin)
) -> dict:
    _check_csrf(request)
    return user


def require_form_csrf(
    request: Request,
    csrf_token: str = Form(""),
    user: dict = Depends(get_current_user),
) -> dict:
    """CSRF check for the no-JavaScript form fallback (hidden input)."""
    expected = getattr(request.state, "csrf_token", "")
    if not expected or not csrf_token or not hmac.compare_digest(csrf_token, expected):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "INVALID_CSRF",
                "message": "Invalid or missing CSRF token.",
            },
        )
    return user
