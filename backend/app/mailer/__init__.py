"""Sending email. Routers get a sender from the `get_mailer` dependency (None = not set up)."""

from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from app.config import get_settings
from app.mailer.base import EmailError, EmailSender, OutgoingEmail
from app.mailer.resend import ResendEmailSender

__all__ = ["EmailError", "EmailSender", "Mailer", "OutgoingEmail", "get_mailer"]


@lru_cache
def _resend() -> ResendEmailSender:
    settings = get_settings()
    assert settings.resend_api_key is not None
    return ResendEmailSender(
        api_key=settings.resend_api_key.get_secret_value(), sender=settings.email_from
    )


def get_mailer() -> EmailSender | None:
    return _resend() if get_settings().resend_api_key is not None else None


Mailer = Annotated[EmailSender | None, Depends(get_mailer)]
