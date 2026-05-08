"""
Unit tests for services.alert_engine.digest.format_digest and build_message.

build_digest_rows() requires a DB connection so it is covered in integration tests.
format_digest() and notifier.build_message() are pure functions and tested here.
"""

import uuid

import pytest

from services.alert_engine.digest import DigestEntry, format_digest
from services.alert_engine.notifier import build_message


class TestFormatDigest:
    def _entry(self, count=3, channel="email"):
        return DigestEntry(
            user_id=uuid.uuid4(),
            channel=channel,
            contact="user@example.com",
            alert_count=count,
            lines=[
                "• Foreclosure — property abc-123  score 82",
                "• Tax Delinquency — property def-456",
                "• Probate — property ghi-789",
            ][:count],
        )

    def test_subject_contains_count(self):
        subject, _ = format_digest(self._entry(count=3))
        assert "3" in subject

    def test_subject_mentions_digest(self):
        subject, _ = format_digest(self._entry())
        assert "digest" in subject.lower()

    def test_body_contains_all_lines(self):
        entry = self._entry(count=3)
        _, body = format_digest(entry)
        for line in entry.lines:
            assert line in body

    def test_single_alert_count(self):
        subject, _ = format_digest(self._entry(count=1))
        assert "1" in subject

    def test_body_has_header(self):
        _, body = format_digest(self._entry())
        assert "24 hours" in body or "alerts" in body.lower()


class TestBuildMessage:
    def test_subject_contains_event_type(self):
        subject, _ = build_message("foreclosure", "travis", str(uuid.uuid4()))
        assert "Foreclosure" in subject

    def test_subject_contains_county(self):
        subject, _ = build_message("foreclosure", "travis", str(uuid.uuid4()))
        assert "Travis" in subject

    def test_body_contains_property_id(self):
        pid = str(uuid.uuid4())
        _, body = build_message("tax_delinquency", "hays", pid)
        assert pid in body

    def test_underscores_replaced_in_subject(self):
        subject, _ = build_message("tax_delinquency", "travis", str(uuid.uuid4()))
        assert "_" not in subject

    def test_underscores_replaced_in_body(self):
        _, body = build_message("tax_delinquency", "travis", str(uuid.uuid4()))
        assert "tax_delinquency" not in body

    def test_returns_two_strings(self):
        result = build_message("probate", "williamson", str(uuid.uuid4()))
        assert len(result) == 2
        assert all(isinstance(s, str) for s in result)
