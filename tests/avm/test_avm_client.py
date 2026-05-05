"""
Unit tests for the AVM service client — no DB, no Estated API calls.

Covers:
  - _parse_estated_response: valuations block present
  - _parse_estated_response: valuations block absent, falls back to assessments
  - _parse_estated_response: fully empty response (graceful zero)
  - get_avm: cache hit skips API call
  - get_avm: cache miss triggers API call and persists result
  - get_avm: force_refresh bypasses cache
"""

from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.avm_service.client import (
    AvmResult,
    _AVM_MAX_AGE_DAYS,
    _parse_estated_response,
    get_avm,
)


# ── _parse_estated_response ───────────────────────────────────────────────────

class TestParseEstatedResponse:
    def test_valuations_block_present(self):
        data = {
            "data": {
                "valuations": [
                    {"value": 425000, "confidence": 87.5, "date": "2026-04-01"}
                ]
            }
        }
        avm, confidence, val_date = _parse_estated_response(data)
        assert avm == pytest.approx(425_000)
        assert confidence == pytest.approx(87.5)
        assert val_date == date(2026, 4, 1)

    def test_assessments_fallback_when_no_valuations(self):
        data = {
            "data": {
                "assessments": [
                    {"total_assessed_value": 310000}
                ]
            }
        }
        avm, confidence, val_date = _parse_estated_response(data)
        assert avm == pytest.approx(310_000)
        assert confidence is None
        assert val_date == date.today()

    def test_empty_response_returns_zero(self):
        avm, confidence, val_date = _parse_estated_response({})
        assert avm == pytest.approx(0.0)
        assert confidence is None

    def test_valuations_missing_date_defaults_to_today(self):
        data = {"data": {"valuations": [{"value": 200000, "confidence": None}]}}
        _, _, val_date = _parse_estated_response(data)
        assert val_date == date.today()

    def test_valuations_missing_confidence_returns_none(self):
        data = {"data": {"valuations": [{"value": 300000}]}}
        _, confidence, _ = _parse_estated_response(data)
        assert confidence is None


# ── get_avm: cache logic ──────────────────────────────────────────────────────

class TestGetAvmCacheLogic:
    @pytest.mark.asyncio
    async def test_cache_hit_skips_api(self):
        pool = MagicMock()
        prop_id = uuid.uuid4()

        cached = AvmResult(
            avm=350_000,
            confidence_score=90.0,
            valuation_date=date.today(),
            provider="estated",
            raw_response={},
            from_cache=True,
        )

        with patch(
            "services.avm_service.client._fetch_cached",
            new=AsyncMock(return_value=cached),
        ) as mock_cache, patch(
            "services.avm_service.client._call_estated",
            new=AsyncMock(),
        ) as mock_api:
            result = await get_avm(pool, prop_id, "123 Main", "Austin")

        mock_cache.assert_awaited_once()
        mock_api.assert_not_awaited()
        assert result.from_cache is True
        assert result.avm == pytest.approx(350_000)

    @pytest.mark.asyncio
    async def test_cache_miss_calls_api_and_persists(self):
        pool = MagicMock()
        prop_id = uuid.uuid4()

        raw = {"data": {"valuations": [{"value": 410000, "confidence": 80.0, "date": "2026-04-15"}]}}

        with patch(
            "services.avm_service.client._fetch_cached",
            new=AsyncMock(return_value=None),
        ), patch(
            "services.avm_service.client._call_estated",
            new=AsyncMock(return_value=raw),
        ) as mock_api, patch(
            "services.avm_service.client._persist_valuation",
            new=AsyncMock(),
        ) as mock_persist:
            result = await get_avm(pool, prop_id, "456 Oak", "Austin")

        mock_api.assert_awaited_once()
        mock_persist.assert_awaited_once()
        assert result.from_cache is False
        assert result.avm == pytest.approx(410_000)
        assert result.confidence_score == pytest.approx(80.0)

    @pytest.mark.asyncio
    async def test_force_refresh_bypasses_cache(self):
        pool = MagicMock()
        prop_id = uuid.uuid4()

        raw = {"data": {"valuations": [{"value": 500000, "confidence": 95.0, "date": "2026-05-01"}]}}

        with patch(
            "services.avm_service.client._fetch_cached",
            new=AsyncMock(return_value=None),
        ) as mock_cache, patch(
            "services.avm_service.client._call_estated",
            new=AsyncMock(return_value=raw),
        ) as mock_api, patch(
            "services.avm_service.client._persist_valuation",
            new=AsyncMock(),
        ):
            result = await get_avm(pool, prop_id, "789 Pine", "Austin", force_refresh=True)

        # _fetch_cached must not be called when force_refresh=True
        mock_cache.assert_not_awaited()
        mock_api.assert_awaited_once()
        assert result.from_cache is False
