"""
Unit tests for services.alert_engine.consumer._parse_message.

The full process_event / run_consumer paths require SQS + DB and are
covered in integration tests. _parse_message() is pure and tested here.
"""

import json
import uuid

import pytest

from services.alert_engine.consumer import _parse_message


def _body(**kw):
    defaults = dict(
        event_id=str(uuid.uuid4()),
        property_id=str(uuid.uuid4()),
        event_type="foreclosure",
        county="travis",
    )
    defaults.update(kw)
    return json.dumps(defaults)


class TestParseMessage:
    def test_valid_minimal_message(self):
        msg = _parse_message(_body())
        assert msg is not None
        assert msg.event_type == "foreclosure"
        assert msg.county == "travis"
        assert msg.distress_score is None
        assert msg.equity_pct is None

    def test_valid_message_with_scores(self):
        msg = _parse_message(_body(distress_score=82.5, equity_pct=35.0))
        assert msg.distress_score == pytest.approx(82.5)
        assert msg.equity_pct == pytest.approx(35.0)

    def test_uuids_are_parsed(self):
        eid = str(uuid.uuid4())
        pid = str(uuid.uuid4())
        msg = _parse_message(_body(event_id=eid, property_id=pid))
        assert str(msg.event_id) == eid
        assert str(msg.property_id) == pid

    def test_invalid_json_returns_none(self):
        assert _parse_message("not-json") is None

    def test_missing_required_field_returns_none(self):
        body = json.dumps({"event_id": str(uuid.uuid4()), "event_type": "foreclosure"})
        assert _parse_message(body) is None

    def test_invalid_uuid_returns_none(self):
        assert _parse_message(_body(event_id="not-a-uuid")) is None

    def test_all_event_types_parse(self):
        for et in ("foreclosure", "tax_delinquency", "probate", "preforeclosure"):
            msg = _parse_message(_body(event_type=et))
            assert msg is not None
            assert msg.event_type == et
