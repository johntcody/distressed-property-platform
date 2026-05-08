"""
Unit tests for services.alert_engine.matcher.match_subscriptions.

Covers:
  - No subscriptions → empty result
  - Subscription with all-NULL filters matches every event
  - County filter: match, no-match, case-sensitive exact
  - event_types filter: match, no-match, multi-type list
  - min_distress_score: match at threshold, fail below threshold,
    fail when score is None
  - min_equity_pct: match at threshold, fail below threshold,
    fail when equity_pct is None
  - Multiple filters: all must pass (AND logic)
  - Multiple subscriptions: only matching ones returned
"""

import uuid

import pytest

from services.alert_engine.matcher import match_subscriptions
from services.alert_engine.models import EventMessage, Subscription


def _event(**kw):
    defaults = dict(
        event_id=uuid.uuid4(),
        property_id=uuid.uuid4(),
        event_type="foreclosure",
        county="travis",
        distress_score=None,
        equity_pct=None,
    )
    defaults.update(kw)
    return EventMessage(**defaults)


def _sub(**kw):
    defaults = dict(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        channel="email",
        contact="user@example.com",
        county=None,
        event_types=None,
        min_distress_score=None,
        min_equity_pct=None,
    )
    defaults.update(kw)
    return Subscription(**defaults)


# ── basic ─────────────────────────────────────────────────────────────────────

class TestBasic:
    def test_no_subscriptions_returns_empty(self):
        assert match_subscriptions(_event(), []) == []

    def test_all_null_filters_matches_any_event(self):
        sub = _sub()
        result = match_subscriptions(_event(), [sub])
        assert result == [sub]

    def test_returns_subscription_object_not_copy(self):
        sub = _sub()
        result = match_subscriptions(_event(), [sub])
        assert result[0] is sub


# ── county filter ─────────────────────────────────────────────────────────────

class TestCountyFilter:
    def test_county_match(self):
        sub = _sub(county="travis")
        assert match_subscriptions(_event(county="travis"), [sub]) == [sub]

    def test_county_no_match(self):
        sub = _sub(county="hays")
        assert match_subscriptions(_event(county="travis"), [sub]) == []

    def test_county_none_matches_all(self):
        sub = _sub(county=None)
        assert match_subscriptions(_event(county="williamson"), [sub]) == [sub]

    def test_county_is_case_sensitive(self):
        sub = _sub(county="Travis")
        assert match_subscriptions(_event(county="travis"), [sub]) == []


# ── event_types filter ────────────────────────────────────────────────────────

class TestEventTypeFilter:
    def test_event_type_in_list_matches(self):
        sub = _sub(event_types=["foreclosure", "probate"])
        assert match_subscriptions(_event(event_type="foreclosure"), [sub]) == [sub]

    def test_event_type_not_in_list_no_match(self):
        sub = _sub(event_types=["probate"])
        assert match_subscriptions(_event(event_type="foreclosure"), [sub]) == []

    def test_event_types_none_matches_all(self):
        sub = _sub(event_types=None)
        assert match_subscriptions(_event(event_type="tax_delinquency"), [sub]) == [sub]

    def test_single_type_list(self):
        sub = _sub(event_types=["tax_delinquency"])
        assert match_subscriptions(_event(event_type="tax_delinquency"), [sub]) == [sub]


# ── distress score filter ─────────────────────────────────────────────────────

class TestDistressScoreFilter:
    def test_score_at_threshold_matches(self):
        sub = _sub(min_distress_score=70.0)
        assert match_subscriptions(_event(distress_score=70.0), [sub]) == [sub]

    def test_score_above_threshold_matches(self):
        sub = _sub(min_distress_score=70.0)
        assert match_subscriptions(_event(distress_score=95.0), [sub]) == [sub]

    def test_score_below_threshold_no_match(self):
        sub = _sub(min_distress_score=70.0)
        assert match_subscriptions(_event(distress_score=60.0), [sub]) == []

    def test_score_none_fails_when_threshold_set(self):
        sub = _sub(min_distress_score=50.0)
        assert match_subscriptions(_event(distress_score=None), [sub]) == []

    def test_score_threshold_none_matches_regardless(self):
        sub = _sub(min_distress_score=None)
        assert match_subscriptions(_event(distress_score=None), [sub]) == [sub]


# ── equity pct filter ─────────────────────────────────────────────────────────

class TestEquityPctFilter:
    def test_equity_at_threshold_matches(self):
        sub = _sub(min_equity_pct=25.0)
        assert match_subscriptions(_event(equity_pct=25.0), [sub]) == [sub]

    def test_equity_above_threshold_matches(self):
        sub = _sub(min_equity_pct=25.0)
        assert match_subscriptions(_event(equity_pct=60.0), [sub]) == [sub]

    def test_equity_below_threshold_no_match(self):
        sub = _sub(min_equity_pct=25.0)
        assert match_subscriptions(_event(equity_pct=10.0), [sub]) == []

    def test_equity_none_fails_when_threshold_set(self):
        sub = _sub(min_equity_pct=20.0)
        assert match_subscriptions(_event(equity_pct=None), [sub]) == []

    def test_equity_threshold_none_matches_regardless(self):
        sub = _sub(min_equity_pct=None)
        assert match_subscriptions(_event(equity_pct=None), [sub]) == [sub]


# ── multi-filter AND logic ────────────────────────────────────────────────────

class TestMultiFilter:
    def test_all_filters_pass(self):
        sub = _sub(county="travis", event_types=["foreclosure"],
                   min_distress_score=60.0, min_equity_pct=20.0)
        event = _event(county="travis", event_type="foreclosure",
                       distress_score=80.0, equity_pct=30.0)
        assert match_subscriptions(event, [sub]) == [sub]

    def test_one_filter_fails_blocks_match(self):
        sub = _sub(county="travis", event_types=["foreclosure"],
                   min_distress_score=60.0, min_equity_pct=20.0)
        # county wrong
        event = _event(county="hays", event_type="foreclosure",
                       distress_score=80.0, equity_pct=30.0)
        assert match_subscriptions(event, [sub]) == []

    def test_multiple_subscriptions_partial_match(self):
        sub_match = _sub(county="travis")
        sub_no    = _sub(county="hays")
        result = match_subscriptions(_event(county="travis"), [sub_match, sub_no])
        assert result == [sub_match]

    def test_multiple_subscriptions_all_match(self):
        sub1 = _sub(county=None)
        sub2 = _sub(county="travis")
        result = match_subscriptions(_event(county="travis"), [sub1, sub2])
        assert len(result) == 2
