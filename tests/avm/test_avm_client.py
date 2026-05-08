"""
Unit tests for the AVM service client — no DB, no external API calls.

Covers:
  - _parse_attom_response: AVM add-on block present
  - _parse_attom_response: AVM block absent, falls back to assessed value
  - _parse_attom_response: fully empty response (graceful zero)
  - _parse_attom_response: confidence derived from high/low spread
  - _parse_attom_response: assessment year → valuation_date Jan 1
  - get_avm: no provider configured returns None
  - get_avm: cache hit skips API call
  - get_avm: cache miss calls API and persists result
  - get_avm: force_refresh bypasses cache
"""

from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.avm_service.client import (
    AvmResult,
    _parse_attom_response,
    get_avm,
)


# ── _parse_attom_response ─────────────────────────────────────────────────────

class TestParseAttomResponse:
    def test_avm_block_present(self):
        data = {
            "property": [{
                "avm": {"amount": {"value": 425000, "low": 400000, "high": 450000}},
                "assessment": {"tax": {"taxyear": "2025"}},
            }]
        }
        avm, confidence, val_date = _parse_attom_response(data)
        assert avm == pytest.approx(425_000)
        assert confidence is not None
        assert val_date == date(2025, 1, 1)

    def test_confidence_from_tight_spread(self):
        # spread = (430k - 420k) / 425k = ~2.35% → confidence ≈ 97.65
        data = {
            "property": [{
                "avm": {"amount": {"value": 425000, "low": 420000, "high": 430000}},
                "assessment": {"tax": {}},
            }]
        }
        _, confidence, _ = _parse_attom_response(data)
        assert confidence == pytest.approx(100 - (10000 / 425000 * 100), rel=1e-3)

    def test_assessed_value_fallback(self):
        data = {
            "property": [{
                "assessment": {
                    "assessed": {"assdttlvalue": 310000},
                    "tax": {"taxyear": "2024"},
                }
            }]
        }
        avm, confidence, val_date = _parse_attom_response(data)
        assert avm == pytest.approx(310_000)
        assert confidence is None
        assert val_date == date(2024, 1, 1)

    def test_empty_response_returns_zero(self):
        avm, confidence, val_date = _parse_attom_response({})
        assert avm == pytest.approx(0.0)
        assert confidence is None
        assert val_date == date.today()

    def test_no_taxyear_defaults_to_today(self):
        data = {"property": [{"assessment": {"assessed": {"assdttlvalue": 200000}, "tax": {}}}]}
        _, _, val_date = _parse_attom_response(data)
        assert val_date == date.today()


# ── get_avm: provider / cache logic ──────────────────────────────────────────

class TestGetAvmProviderLogic:
    @pytest.mark.asyncio
    async def test_no_provider_returns_none(self):
        pool = MagicMock()
        prop_id = uuid.uuid4()

        with patch("services.avm_service.client._AVM_PROVIDER", ""):
            result = await get_avm(pool, prop_id, "123 Main", "Austin")

        assert result is None

    @pytest.mark.asyncio
    async def test_cache_hit_skips_api(self):
        pool = MagicMock()
        prop_id = uuid.uuid4()

        cached = AvmResult(
            avm=350_000,
            confidence_score=90.0,
            valuation_date=date.today(),
            provider="attom",
            raw_response={},
            from_cache=True,
        )

        with patch("services.avm_service.client._AVM_PROVIDER", "attom"), \
             patch("services.avm_service.client._fetch_cached", new=AsyncMock(return_value=cached)), \
             patch("services.avm_service.client._call_attom", new=AsyncMock()) as mock_api:
            result = await get_avm(pool, prop_id, "123 Main", "Austin")

        mock_api.assert_not_awaited()
        assert result.from_cache is True
        assert result.avm == pytest.approx(350_000)

    @pytest.mark.asyncio
    async def test_cache_miss_calls_attom_and_persists(self):
        pool = MagicMock()
        prop_id = uuid.uuid4()

        raw = {
            "property": [{
                "avm": {"amount": {"value": 410000, "low": 395000, "high": 425000}},
                "assessment": {"tax": {"taxyear": "2025"}},
            }]
        }

        with patch("services.avm_service.client._AVM_PROVIDER", "attom"), \
             patch("services.avm_service.client._fetch_cached", new=AsyncMock(return_value=None)), \
             patch("services.avm_service.client._call_attom", new=AsyncMock(return_value=raw)), \
             patch("services.avm_service.client._persist_valuation", new=AsyncMock()) as mock_persist:
            result = await get_avm(pool, prop_id, "456 Oak", "Austin")

        mock_persist.assert_awaited_once()
        assert result.from_cache is False
        assert result.avm == pytest.approx(410_000)
        assert result.provider == "attom"

    @pytest.mark.asyncio
    async def test_force_refresh_bypasses_cache(self):
        pool = MagicMock()
        prop_id = uuid.uuid4()

        raw = {
            "property": [{
                "avm": {"amount": {"value": 500000, "low": 490000, "high": 510000}},
                "assessment": {"tax": {"taxyear": "2025"}},
            }]
        }

        with patch("services.avm_service.client._AVM_PROVIDER", "attom"), \
             patch("services.avm_service.client._fetch_cached", new=AsyncMock()) as mock_cache, \
             patch("services.avm_service.client._call_attom", new=AsyncMock(return_value=raw)), \
             patch("services.avm_service.client._persist_valuation", new=AsyncMock()):
            result = await get_avm(pool, prop_id, "789 Pine", "Austin", force_refresh=True)

        mock_cache.assert_not_awaited()
        assert result.from_cache is False
