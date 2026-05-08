"""Notification dispatch stubs.

Each channel function accepts a contact address and a message body.
Replace the stub implementations with real provider SDKs
(SES, Twilio, FCM) without changing the call sites.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def send_email(contact: str, subject: str, body: str) -> None:
    # TODO: replace with boto3 SES call
    logger.info("EMAIL → %s | %s", contact, subject)


def send_sms(contact: str, body: str) -> None:
    # TODO: replace with Twilio / SNS SMS call
    logger.info("SMS → %s | %s", contact, body[:60])


def send_push(contact: str, title: str, body: str) -> None:
    # TODO: replace with FCM / APNs call
    logger.info("PUSH → %s | %s", contact, title)


def dispatch(channel: str, contact: str, subject: str, body: str) -> None:
    """Route to the correct channel dispatcher."""
    if channel == "email":
        send_email(contact, subject, body)
    elif channel == "sms":
        send_sms(contact, body)
    elif channel == "push":
        send_push(contact, subject, body)
    else:
        logger.warning("Unknown channel %r — alert not sent to %s", channel, contact)


def build_message(event_type: str, county: str, property_id: str) -> tuple[str, str]:
    """Return (subject, body) for a new-event alert."""
    subject = f"New {event_type.replace('_', ' ').title()} alert — {county.title()} County"
    body = (
        f"A new {event_type.replace('_', ' ')} filing has been detected in "
        f"{county.title()} County.\n\nProperty ID: {property_id}\n\n"
        "Log in to the platform to view details."
    )
    return subject, body
