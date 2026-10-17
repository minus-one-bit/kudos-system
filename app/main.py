"""FastAPI application factory and middleware wiring."""

from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import load_settings
from .db import connect, init_db
from .routers import admin, api, auth, pages
from .services import ServiceError, get_session_user

BASE_DIR = Path(__file__).resolve().parent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)
logger = logging.getLogger("kudos")

CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "img-src 'self' data:; "
    "style-src 'self'; "
    "script-src 'self'; "
    "connect-src 'self'; "
    "font-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)


def create_app(db_path: str | None = None) -> FastAPI:
    settings = load_settings(db_path)
    init_db(settings.db_path)

    app = FastAPI(
        title="Kudos",
        version="1.0.0",
        description="Internal peer recognition feature.",
        # The interactive docs load assets from a CDN and are incompatible with
        # the strict CSP below; the OpenAPI schema remains at /openapi.json.
        docs_url=None,
        redoc_url=None,
    )
    app.state.settings = settings
    app.state.db_path = settings.db_path

    @app.middleware("http")
    async def session_middleware(request: Request, call_next):
        request.state.user = None
        request.state.csrf_token = ""
        token = request.cookies.get(settings.session_cookie)
        if token:
            connection = connect(settings.db_path)
            try:
                user, csrf_token = get_session_user(connection, token)
            finally:
                connection.close()
            request.state.user = user
            request.state.csrf_token = csrf_token or ""
        return await call_next(request)

    @app.middleware("http")
    async def security_and_logging_middleware(request: Request, call_next):
        request_id = uuid.uuid4().hex[:12]
        started = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - started) * 1000

        response.headers["X-Request-ID"] = request_id
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("Content-Security-Policy", CONTENT_SECURITY_POLICY)

        if request.url.path.startswith("/static/"):
            response.headers.setdefault("Cache-Control", "public, max-age=86400")
        elif request.url.path.startswith("/api") or request.url.path == "/healthz":
            response.headers.setdefault("Cache-Control", "no-store")
        else:
            response.headers.setdefault("Cache-Control", "no-store")

        logger.info(
            "%s %s -> %s %.1fms id=%s",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
            request_id,
        )
        return response

    @app.exception_handler(ServiceError)
    async def service_error_handler(request: Request, exc: ServiceError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Request validation failed.",
                }
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(request: Request, exc: StarletteHTTPException):
        if request.url.path.startswith("/api"):
            detail = exc.detail
            if isinstance(detail, dict) and "code" in detail:
                error = detail
            else:
                error = {"code": "HTTP_ERROR", "message": str(detail)}
            return JSONResponse(
                status_code=exc.status_code,
                content={"error": error},
                headers=exc.headers,
            )
        return await http_exception_handler(request, exc)

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception):
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        if request.url.path.startswith("/api"):
            return JSONResponse(
                status_code=500,
                content={
                    "error": {
                        "code": "INTERNAL_ERROR",
                        "message": "An unexpected error occurred.",
                    }
                },
            )
        return PlainTextResponse("Internal Server Error", status_code=500)

    app.mount(
        "/static",
        StaticFiles(directory=str(BASE_DIR / "static")),
        name="static",
    )

    app.include_router(auth.router)
    app.include_router(pages.router)
    app.include_router(api.router)
    app.include_router(admin.router)

    return app


app = create_app()
