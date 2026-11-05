"""The Resend adapter, against a mock HTTP transport (no network)."""

import json

import httpx2 as httpx
import pytest

from app.config import RESEND_API_URL
from app.mailer import EmailError, OutgoingEmail
from app.mailer.resend import ResendEmailSender

MESSAGE = OutgoingEmail(to="demo@unify.example.com", subject="Hello", text="Body text")


def _sender(handler) -> tuple[ResendEmailSender, list[httpx.Request]]:  # type: ignore[no-untyped-def]
    seen: list[httpx.Request] = []

    def _record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    sender = ResendEmailSender(
        api_key="re_test_key",
        sender="UNIFY SUITE <onboarding@resend.dev>",
        http_client=httpx.Client(transport=httpx.MockTransport(_record)),
    )
    return sender, seen


def test_sends_plain_text_with_bearer_key() -> None:
    sender, seen = _sender(lambda _: httpx.Response(200, json={"id": "msg_123"}))

    assert sender.send(MESSAGE) == "msg_123"

    [request] = seen
    assert str(request.url) == RESEND_API_URL
    assert request.headers["Authorization"] == "Bearer re_test_key"
    assert json.loads(request.content) == {
        "from": "UNIFY SUITE <onboarding@resend.dev>",
        "to": ["demo@unify.example.com"],
        "subject": "Hello",
        "text": "Body text",
    }


def test_provider_errors_become_email_errors_with_the_reason() -> None:
    sender, _ = _sender(
        lambda _: httpx.Response(
            403, json={"message": "You can only send testing emails to your own address"}
        )
    )

    with pytest.raises(EmailError, match="403: You can only send testing emails"):
        sender.send(MESSAGE)


def test_network_errors_become_email_errors() -> None:
    def _down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    sender, _ = _sender(_down)

    with pytest.raises(EmailError, match="could not reach"):
        sender.send(MESSAGE)


def test_blank_email_settings_count_as_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import Settings

    monkeypatch.setenv("RESEND_API_KEY", "")
    monkeypatch.setenv("EMAIL_REDIRECT_TO", "  ")

    settings = Settings()  # type: ignore[call-arg]

    assert settings.resend_api_key is None and settings.email_redirect_to is None
