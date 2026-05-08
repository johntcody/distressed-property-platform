"""Data models for the Alert Engine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from uuid import UUID


@dataclass(frozen=True)
class EventMessage:
    """Parsed payload from an SQS message (published by each ingestion pipeline)."""
    event_id:       UUID
    property_id:    UUID
    event_type:     str          # foreclosure | tax_delinquency | probate | preforeclosure
    county:         str
    distress_score: Optional[float] = None
    equity_pct:     Optional[float] = None


@dataclass(frozen=True)
class Subscription:
    """Row from alert_subscriptions."""
    id:                 UUID
    user_id:            UUID
    channel:            str          # email | sms | push
    contact:            str
    county:             Optional[str]
    event_types:        Optional[list[str]]
    min_distress_score: Optional[float]
    min_equity_pct:     Optional[float]


@dataclass
class DispatchedAlert:
    """Record to persist in the alerts table after sending."""
    property_id:     UUID
    subscription_id: UUID
    event_id:        UUID
    trigger_type:    str
    trigger_score:   Optional[float]
    channel:         str
    contact:         str
