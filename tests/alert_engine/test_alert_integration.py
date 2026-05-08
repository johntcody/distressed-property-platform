"""
Integration tests for the Alert Engine.

Requires a live Postgres database with all migrations applied (001–013).
Set DATABASE_URL to run; all tests are skipped otherwise.

Tests cover:
  - load_active_subscriptions: returns only active rows, field mapping
  - persist_alert: inserts row, readable back from DB
  - match + persist round-trip: subscription matches event, alert stored
  - build_digest_rows: aggregates last-24-h alerts by user
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
import pytest_asyncio

pytest.importorskip("asyncpg")
import asyncpg  # noqa: E402

from services.alert_engine.digest import build_digest_rows
from services.alert_engine.matcher import match_subscriptions
from services.alert_engine.models import DispatchedAlert, EventMessage
from services.alert_engine.store import load_active_subscriptions, persist_alert

DATABASE_URL = os.environ.get("DATABASE_URL")
skip_no_db = pytest.mark.skipif(
    not DATABASE_URL,
    reason="DATABASE_URL not set — skipping live-DB integration tests",
)


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture(scope="module")
async def pool():
    p = await asyncpg.create_pool(dsn=DATABASE_URL, min_size=1, max_size=3, command_timeout=15)
    yield p
    await p.close()


# ── insert helpers ────────────────────────────────────────────────────────────

async def _insert_user(pool) -> uuid.UUID:
    uid = uuid.uuid4()
    await pool.execute(
        "INSERT INTO users (id, email) VALUES ($1, $2)",
        uid, f"{uid}@test.example",
    )
    return uid


async def _insert_property(pool) -> uuid.UUID:
    pid = uuid.uuid4()
    await pool.execute(
        "INSERT INTO properties (id, address_raw, city, county, state, zip_code)"
        " VALUES ($1, $2, 'Austin', 'travis', 'TX', '78701')",
        pid, f"{pid} Main St",
    )
    return pid


async def _insert_event(pool, pid: uuid.UUID, event_type="foreclosure") -> uuid.UUID:
    eid = uuid.uuid4()
    await pool.execute(
        "INSERT INTO events (id, property_id, event_type, county, filing_date)"
        " VALUES ($1, $2, $3::distress_event_type, 'travis', $4)",
        eid, pid, event_type, date.today(),
    )
    return eid


async def _insert_subscription(pool, uid: uuid.UUID, *, active=True, county=None,
                                event_types=None, min_distress_score=None,
                                min_equity_pct=None, channel="email") -> uuid.UUID:
    sid = uuid.uuid4()
    await pool.execute(
        """
        INSERT INTO alert_subscriptions
            (id, user_id, county, event_types, min_distress_score,
             min_equity_pct, channel, contact, active)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        """,
        sid, uid, county, event_types, min_distress_score,
        min_equity_pct, channel, f"contact-{sid}@test.example", active,
    )
    return sid


async def _insert_alert(pool, pid, sid, eid, trigger_type="foreclosure",
                        sent_at=None) -> uuid.UUID:
    aid = uuid.uuid4()
    sent_at = sent_at or datetime.now(tz=timezone.utc)
    await pool.execute(
        """
        INSERT INTO alerts
            (id, property_id, subscription_id, event_id,
             trigger_type, channel, contact, sent_at)
        VALUES ($1, $2, $3, $4, $5, 'email', 'test@test.example', $6)
        """,
        aid, pid, sid, eid, trigger_type, sent_at,
    )
    return aid


async def _cleanup_user(pool, uid):
    # Deleting the user cascades to alert_subscriptions (ON DELETE CASCADE).
    # alerts.subscription_id is ON DELETE SET NULL, so alert rows survive with
    # subscription_id = NULL — they are cleaned up by _cleanup_property().
    await pool.execute("DELETE FROM users WHERE id = $1", uid)


async def _cleanup_property(pool, pid):
    await pool.execute("DELETE FROM events    WHERE property_id = $1", pid)
    await pool.execute("DELETE FROM alerts    WHERE property_id = $1", pid)
    await pool.execute("DELETE FROM properties WHERE id = $1", pid)


# ── load_active_subscriptions ─────────────────────────────────────────────────

@skip_no_db
class TestLoadActiveSubscriptions:
    @pytest.mark.asyncio
    async def test_returns_active_subscriptions(self, pool):
        uid = await _insert_user(pool)
        try:
            sid = await _insert_subscription(pool, uid, county="travis", active=True)
            subs = await load_active_subscriptions(pool)
            ids = [s.id for s in subs]
            assert sid in ids
        finally:
            await _cleanup_user(pool, uid)

    @pytest.mark.asyncio
    async def test_excludes_inactive_subscriptions(self, pool):
        uid = await _insert_user(pool)
        try:
            sid = await _insert_subscription(pool, uid, active=False)
            subs = await load_active_subscriptions(pool)
            ids = [s.id for s in subs]
            assert sid not in ids
        finally:
            await _cleanup_user(pool, uid)

    @pytest.mark.asyncio
    async def test_county_field_mapped(self, pool):
        uid = await _insert_user(pool)
        try:
            sid = await _insert_subscription(pool, uid, county="hays")
            subs = await load_active_subscriptions(pool)
            sub = next(s for s in subs if s.id == sid)
            assert sub.county == "hays"
        finally:
            await _cleanup_user(pool, uid)

    @pytest.mark.asyncio
    async def test_score_threshold_mapped(self, pool):
        uid = await _insert_user(pool)
        try:
            sid = await _insert_subscription(pool, uid, min_distress_score=65.0)
            subs = await load_active_subscriptions(pool)
            sub = next(s for s in subs if s.id == sid)
            assert sub.min_distress_score == pytest.approx(65.0)
        finally:
            await _cleanup_user(pool, uid)


# ── persist_alert ─────────────────────────────────────────────────────────────

@skip_no_db
class TestPersistAlert:
    @pytest.mark.asyncio
    async def test_alert_inserted(self, pool):
        uid = await _insert_user(pool)
        pid = await _insert_property(pool)
        try:
            eid = await _insert_event(pool, pid)
            sid = await _insert_subscription(pool, uid)
            alert = DispatchedAlert(
                property_id=pid, subscription_id=sid, event_id=eid,
                trigger_type="foreclosure", trigger_score=80.0,
                channel="email", contact="x@test.com",
            )
            await persist_alert(pool, alert)
            row = await pool.fetchrow(
                "SELECT * FROM alerts WHERE property_id = $1 AND subscription_id = $2",
                pid, sid,
            )
            assert row is not None
            assert row["trigger_type"] == "foreclosure"
        finally:
            await _cleanup_property(pool, pid)
            await _cleanup_user(pool, uid)


# ── match + persist round-trip ────────────────────────────────────────────────

@skip_no_db
class TestMatchAndPersist:
    @pytest.mark.asyncio
    async def test_matching_subscription_produces_stored_alert(self, pool):
        uid = await _insert_user(pool)
        pid = await _insert_property(pool)
        try:
            eid = await _insert_event(pool, pid, "foreclosure")
            sid = await _insert_subscription(
                pool, uid, county="travis", event_types=["foreclosure"],
            )
            subs = await load_active_subscriptions(pool)
            event = EventMessage(
                event_id=eid, property_id=pid,
                event_type="foreclosure", county="travis",
                distress_score=85.0,
            )
            matched = match_subscriptions(event, subs)
            assert any(s.id == sid for s in matched)

            for sub in matched:
                if sub.id != sid:
                    continue
                alert = DispatchedAlert(
                    property_id=pid, subscription_id=sub.id, event_id=eid,
                    trigger_type=event.event_type, trigger_score=event.distress_score,
                    channel=sub.channel, contact=sub.contact,
                )
                await persist_alert(pool, alert)

            count = await pool.fetchval(
                "SELECT COUNT(*) FROM alerts WHERE property_id = $1 AND subscription_id = $2",
                pid, sid,
            )
            assert count == 1
        finally:
            await _cleanup_property(pool, pid)
            await _cleanup_user(pool, uid)

    @pytest.mark.asyncio
    async def test_non_matching_subscription_produces_no_alert(self, pool):
        uid = await _insert_user(pool)
        pid = await _insert_property(pool)
        try:
            eid = await _insert_event(pool, pid, "probate")
            sid = await _insert_subscription(
                pool, uid, event_types=["foreclosure"],  # won't match probate
            )
            subs = await load_active_subscriptions(pool)
            event = EventMessage(
                event_id=eid, property_id=pid,
                event_type="probate", county="travis",
            )
            matched = match_subscriptions(event, subs)
            assert not any(s.id == sid for s in matched)
        finally:
            await _cleanup_property(pool, pid)
            await _cleanup_user(pool, uid)


# ── build_digest_rows ─────────────────────────────────────────────────────────

@skip_no_db
class TestBuildDigestRows:
    @pytest.mark.asyncio
    async def test_user_with_recent_alert_appears_in_digest(self, pool):
        uid = await _insert_user(pool)
        pid = await _insert_property(pool)
        try:
            eid = await _insert_event(pool, pid)
            sid = await _insert_subscription(pool, uid)
            await _insert_alert(pool, pid, sid, eid)
            entries = await build_digest_rows(pool)
            user_ids = [e.user_id for e in entries]
            assert uid in user_ids
        finally:
            await _cleanup_property(pool, pid)
            await _cleanup_user(pool, uid)

    @pytest.mark.asyncio
    async def test_old_alert_excluded_from_digest(self, pool):
        uid = await _insert_user(pool)
        pid = await _insert_property(pool)
        try:
            eid = await _insert_event(pool, pid)
            sid = await _insert_subscription(pool, uid)
            two_days_ago = datetime.now(tz=timezone.utc) - timedelta(hours=49)
            await _insert_alert(pool, pid, sid, eid, sent_at=two_days_ago)
            entries = await build_digest_rows(pool)
            user_ids = [e.user_id for e in entries]
            assert uid not in user_ids
        finally:
            await _cleanup_property(pool, pid)
            await _cleanup_user(pool, uid)

    @pytest.mark.asyncio
    async def test_digest_entry_has_correct_alert_count(self, pool):
        uid = await _insert_user(pool)
        pid = await _insert_property(pool)
        try:
            eid1 = await _insert_event(pool, pid, "foreclosure")
            eid2 = await _insert_event(pool, pid, "probate")
            sid = await _insert_subscription(pool, uid)
            await _insert_alert(pool, pid, sid, eid1)
            await _insert_alert(pool, pid, sid, eid2)
            entries = await build_digest_rows(pool)
            entry = next(e for e in entries if e.user_id == uid)
            assert entry.alert_count == 2
        finally:
            await _cleanup_property(pool, pid)
            await _cleanup_user(pool, uid)
