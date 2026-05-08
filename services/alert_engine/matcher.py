"""Subscription matching logic.

match_subscriptions() is a pure function — no DB or network I/O — which
makes it straightforward to unit-test exhaustively.
"""

from __future__ import annotations

from typing import Sequence

from .models import EventMessage, Subscription


def match_subscriptions(
    event: EventMessage,
    subscriptions: Sequence[Subscription],
) -> list[Subscription]:
    """Return subscriptions whose filters all match the given event."""
    matched = []
    for sub in subscriptions:
        if not _matches(event, sub):
            continue
        matched.append(sub)
    return matched


def _matches(event: EventMessage, sub: Subscription) -> bool:
    # county filter: None means "all counties"; normalize both sides to avoid
    # missed alerts when a subscription stores "Travis" but events carry "travis"
    if sub.county is not None and sub.county.lower() != event.county.lower():
        return False

    # event_type filter: None means "all types"; [] means "no types" (never matches)
    if sub.event_types is not None and event.event_type not in sub.event_types:
        return False

    # distress score threshold
    if sub.min_distress_score is not None:
        if event.distress_score is None or event.distress_score < sub.min_distress_score:
            return False

    # equity pct threshold
    if sub.min_equity_pct is not None:
        if event.equity_pct is None or event.equity_pct < sub.min_equity_pct:
            return False

    return True
