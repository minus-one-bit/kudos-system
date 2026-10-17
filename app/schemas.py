"""Request models. Response payloads are plain dicts built by the services."""

from pydantic import BaseModel


class KudosCreate(BaseModel):
    recipient_id: int
    message: str = ""


class ModerationRequest(BaseModel):
    reason: str = ""
