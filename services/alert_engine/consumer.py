"""SQS consumer loop for the Alert Engine.

Architecture:
  - Each ingestion pipeline publishes a JSON message to the SQS queue
    after inserting a row into the `events` table.
  - This consumer polls the queue, matches each event against active
    subscriptions, dispatches notifications, and records the alert.

Message schema (JSON):
  {
    "event_id":       "<uuid>",
    "property_id":    "<uuid>",
    "event_type":     "foreclosure",
    "county":         "travis",
    "distress_score": 82.5,       // optional
    "equity_pct":     35.0        // optional
  }
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from typing import Optional

from .matcher import match_subscriptions
from .models import DispatchedAlert, EventMessage
from .notifier import build_message, dispatch
from .store import load_active_subscriptions, persist_alert

logger = logging.getLogger(__name__)

_QUEUE_URL = os.environ.get("ALERT_QUEUE_URL", "")
_MAX_MESSAGES = 10          # SQS batch size limit
_WAIT_SECONDS = 20          # long-polling window


def _parse_message(body: str) -> Optional[EventMessage]:
    try:
        d = json.loads(body)
        return EventMessage(
            event_id=uuid.UUID(d["event_id"]),
            property_id=uuid.UUID(d["property_id"]),
            event_type=d["event_type"],
            county=d["county"],
            distress_score=d.get("distress_score"),
            equity_pct=d.get("equity_pct"),
        )
    except Exception:
        logger.exception("Failed to parse SQS message body: %s", body[:200])
        return None


async def process_event(pool, sqs_client, event: EventMessage, receipt_handle: str) -> None:
    subscriptions = await load_active_subscriptions(pool)
    matched = match_subscriptions(event, subscriptions)

    for sub in matched:
        subject, body = build_message(
            event.event_type, event.county, str(event.property_id)
        )
        try:
            dispatch(sub.channel, sub.contact, subject, body)
        except Exception:
            logger.exception("Dispatch failed for subscription %s", sub.id)
            continue

        alert = DispatchedAlert(
            property_id=event.property_id,
            subscription_id=sub.id,
            event_id=event.event_id,
            trigger_type=event.event_type,
            trigger_score=event.distress_score,
            channel=sub.channel,
            contact=sub.contact,
        )
        await persist_alert(pool, alert)

    # Delete from queue only after all processing succeeds
    sqs_client.delete_message(QueueUrl=_QUEUE_URL, ReceiptHandle=receipt_handle)
    logger.info(
        "Processed event %s (%s) → %d notification(s)",
        event.event_id, event.event_type, len(matched),
    )


async def run_consumer(pool) -> None:
    """Poll SQS indefinitely. Intended to run as a long-lived async task."""
    import boto3
    sqs = boto3.client("sqs", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    logger.info("Alert consumer started. Queue: %s", _QUEUE_URL)

    while True:
        response = sqs.receive_message(
            QueueUrl=_QUEUE_URL,
            MaxNumberOfMessages=_MAX_MESSAGES,
            WaitTimeSeconds=_WAIT_SECONDS,
        )
        messages = response.get("Messages", [])

        for msg in messages:
            event = _parse_message(msg["Body"])
            if event is None:
                # Poison-pill: delete so it doesn't block the queue
                sqs.delete_message(QueueUrl=_QUEUE_URL, ReceiptHandle=msg["ReceiptHandle"])
                continue
            await process_event(pool, sqs, event, msg["ReceiptHandle"])
