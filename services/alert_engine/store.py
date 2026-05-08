"""Database helpers for the alert engine."""

from __future__ import annotations

from typing import Sequence
from uuid import UUID

from .models import DispatchedAlert, Subscription

_SUBSCRIPTIONS_SQL = """\
SELECT id, user_id, channel, contact, county, event_types,
       min_distress_score, min_equity_pct
FROM   alert_subscriptions
WHERE  active = TRUE
"""

_INSERT_ALERT_SQL = """\
INSERT INTO alerts
    (property_id, subscription_id, event_id, trigger_type,
     trigger_score, channel, contact)
VALUES ($1, $2, $3, $4, $5, $6, $7)
"""


async def load_active_subscriptions(pool) -> list[Subscription]:
    rows = await pool.fetch(_SUBSCRIPTIONS_SQL)
    return [
        Subscription(
            id=row["id"],
            user_id=row["user_id"],
            channel=row["channel"],
            contact=row["contact"],
            county=row["county"],
            # NULL → None (match all types); [] → [] (match nothing); preserve distinction
            event_types=list(row["event_types"]) if row["event_types"] is not None else None,
            min_distress_score=float(row["min_distress_score"])
                if row["min_distress_score"] is not None else None,
            min_equity_pct=float(row["min_equity_pct"])
                if row["min_equity_pct"] is not None else None,
        )
        for row in rows
    ]


async def persist_alert(pool, alert: DispatchedAlert) -> None:
    await pool.execute(
        _INSERT_ALERT_SQL,
        alert.property_id,
        alert.subscription_id,
        alert.event_id,
        alert.trigger_type,
        alert.trigger_score,
        alert.channel,
        alert.contact,
    )
