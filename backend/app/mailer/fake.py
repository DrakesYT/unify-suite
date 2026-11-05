from app.mailer.base import EmailError, OutgoingEmail


class FakeEmailSender:
    """Records emails instead of sending them. Set `fail_with` to make the next sends fail."""

    def __init__(self) -> None:
        self.sent: list[OutgoingEmail] = []
        self.fail_with: str | None = None

    def send(self, email: OutgoingEmail) -> str:
        if self.fail_with:
            raise EmailError(self.fail_with)
        self.sent.append(email)
        return f"fake-{len(self.sent)}"
