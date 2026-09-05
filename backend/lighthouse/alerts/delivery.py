"""Getting the digest out.

SMTP, because a job alert has to reach the operator when they are not at the
machine, and email is the one channel that already does that on every device
they own. A desktop notification is a nice second and reaches nobody who has
stepped away from the laptop.

The transport is injectable, and the default when nothing is configured is a
recorded no-op rather than an exception. A half-configured alerter that raises
inside the ingest run would take down the freshness pipeline to deliver a
convenience; one that silently claims success would be worse still, so the
result says exactly which of the three happened.
"""

from __future__ import annotations

import logging
import smtplib
from dataclasses import dataclass, field
from email.message import EmailMessage

logger = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class DeliveryResult:
    sent: bool
    reason: str


@dataclass
class CaptureTransport:
    """Keeps messages in memory instead of sending them.

    Used by the tests and by ``--dry-run``, so the whole path from an ingest
    run to a rendered digest can be exercised without an SMTP account and
    without mailing anyone.
    """

    messages: list[EmailMessage] = field(default_factory=list)

    def send(self, message: EmailMessage) -> DeliveryResult:
        self.messages.append(message)
        return DeliveryResult(True, "Captured, not sent (dry run).")


@dataclass(slots=True)
class SmtpTransport:
    host: str
    port: int = 587
    username: str = ""
    password: str = ""
    use_tls: bool = True
    timeout: float = 20.0

    def send(self, message: EmailMessage) -> DeliveryResult:
        try:
            with smtplib.SMTP(self.host, self.port, timeout=self.timeout) as server:
                if self.use_tls:
                    server.starttls()
                if self.username:
                    server.login(self.username, self.password)
                server.send_message(message)
        except (OSError, smtplib.SMTPException) as exc:
            # Reported, never raised past here: an alert is a convenience and
            # must not be able to fail the ingest run it rides on.
            logger.warning("alert delivery failed: %s", exc)
            return DeliveryResult(False, f"Could not send ({type(exc).__name__}: {exc}).")
        return DeliveryResult(True, "Sent.")


def build_message(*, to: str, sender: str, subject: str, body: str) -> EmailMessage:
    message = EmailMessage()
    message["To"] = to
    message["From"] = sender or to
    message["Subject"] = subject
    message.set_content(body)
    return message


def transport_from_settings(settings) -> SmtpTransport | None:
    """The configured transport, or None when alerts are not set up."""
    if not settings.alerts_configured:
        return None
    return SmtpTransport(
        host=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_username,
        password=settings.smtp_password,
        use_tls=settings.smtp_use_tls,
    )
