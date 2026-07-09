from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    body: str


class ConsoleEmailProvider:
    def send(self, message: EmailMessage) -> dict:
        print(f"[mock-email] to={message.to} subject={message.subject}\n{message.body}")
        return {"provider": "console", "status": "queued", "to": message.to}


def email_provider() -> ConsoleEmailProvider:
    provider = os.getenv("NEXUSLEAD_EMAIL_PROVIDER", "console")
    if provider != "console":
        print(f"[mock-email] provider {provider} requested; console provider active for local development")
    return ConsoleEmailProvider()


def notify_outreach_approved(recipient: str, lead_summary: str) -> dict:
    message = EmailMessage(
        to=recipient,
        subject="NexusLead AI outreach draft approved",
        body=f"A human-reviewed outreach draft is approved for: {lead_summary}",
    )
    return email_provider().send(message)
