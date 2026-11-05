"""Resend (https://resend.com) over its HTTPS API: no SMTP ports needed on the VM."""

import logging
import time

import httpx2

from app.config import EMAIL_SEND_TIMEOUT_S, RESEND_API_URL
from app.mailer.base import EmailError, OutgoingEmail

logger = logging.getLogger(__name__)


class ResendEmailSender:
    def __init__(
        self,
        *,
        api_key: str,
        sender: str,
        http_client: httpx2.Client | None = None,  # tests pass a mock transport
    ) -> None:
        self._sender = sender
        self._client = http_client or httpx2.Client(timeout=EMAIL_SEND_TIMEOUT_S)
        self._headers = {"Authorization": f"Bearer {api_key}"}

    def send(self, email: OutgoingEmail) -> str:
        started = time.monotonic()
        try:
            response = self._client.post(
                RESEND_API_URL,
                headers=self._headers,
                json={
                    "from": self._sender,
                    "to": [email.to],
                    "subject": email.subject,
                    "text": email.text,
                },
            )
        except httpx2.HTTPError as exc:
            self._log(started, ok=False, error=type(exc).__name__)
            raise EmailError("could not reach the email service") from exc
        if response.status_code >= 400:
            self._log(started, ok=False, error=f"http_{response.status_code}")
            message = _error_message(response)
            raise EmailError(f"email service returned {response.status_code}: {message}")
        self._log(started, ok=True)
        return str(response.json().get("id", ""))

    @staticmethod
    def _log(started: float, *, ok: bool, error: str | None = None) -> None:
        latency_ms = round((time.monotonic() - started) * 1000)
        logger.info(
            "email_send",
            extra={"provider": "resend", "ok": ok, "error": error, "latency_ms": latency_ms},
        )


def _error_message(response: httpx2.Response) -> str:
    try:
        return str(response.json().get("message", ""))[:200]
    except ValueError:
        return response.text[:200]
