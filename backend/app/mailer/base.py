from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class OutgoingEmail:
    to: str
    subject: str
    text: str


class EmailError(Exception):
    """The email provider refused or could not be reached."""


class EmailSender(Protocol):
    def send(self, email: OutgoingEmail) -> str:
        """Send one plain-text email. Returns the provider's message id; raises EmailError."""
        ...
