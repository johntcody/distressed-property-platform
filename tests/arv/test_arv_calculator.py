"""
Unit tests for the ARV calculator.

Covers:
  - No comps → arv=None, confidence=0, comp_count=0
  - Comp filtering: beds/baths mismatch excluded
  - Comp filtering: sqft outside ±20% excluded
  - Comp filtering: sale_date older than 12 months excluded
  - Single valid comp → confidence=50
  - 3–4 valid comps → confidence=70
  - ≥5 valid comps → confidence=90
  - Weighted ARV math: closer comp weighted more heavily
  - arv_version default
"""

import pytest
from datetime import date, timedelta
from unittest.mock import patch

from services.arv_engine.arv import ARVCalculator, Comp, SubjectProperty

_SUBJECT = SubjectProperty(
    property_id="test-prop-1",
    sqft=1500.0,
    beds=3,
    baths=2.0,
    zip_code="78701",
)

calculator = ARVCalculator()


def _make_comp(
    sale_price: float = 300_000,
    sqft: float = 1500,
    beds: int = 3,
    baths: float = 2.0,
    days_ago: int = 90,
    distance_miles: float = 0.5,
) -> Comp:
    return Comp(
        sale_price=sale_price,
        sqft=sqft,
        beds=beds,
        baths=baths,
        sale_date=date.today() - timedelta(days=days_ago),
        distance_miles=distance_miles,
    )


# ── no comps ──────────────────────────────────────────────────────────────────

class TestNoComps:
    def test_stub_provider_returns_no_comps(self):
        result = calculator.estimate(_SUBJECT)
        assert result.arv is None
        assert result.arv_confidence == pytest.approx(0.0)
        assert result.comp_count == 0

    def test_arv_version_default(self):
        result = calculator.estimate(_SUBJECT)
        assert result.arv_version == "1.0"

    def test_method_is_price_per_sqft(self):
        result = calculator.estimate(_SUBJECT)
        assert result.method == "price_per_sqft"


# ── filtering ─────────────────────────────────────────────────────────────────

class TestFiltering:
    def _estimate_with(self, comps):
        with patch("services.arv_engine.arv._get_comps", return_value=comps):
            return calculator.estimate(_SUBJECT)

    def test_beds_mismatch_excluded(self):
        result = self._estimate_with([_make_comp(beds=4)])
        assert result.comp_count == 0

    def test_baths_mismatch_excluded(self):
        result = self._estimate_with([_make_comp(baths=1.0)])
        assert result.comp_count == 0

    def test_sqft_too_small_excluded(self):
        # 1500 * 0.79 = 1185 → below 1500 * 0.80 = 1200
        result = self._estimate_with([_make_comp(sqft=1185)])
        assert result.comp_count == 0

    def test_sqft_too_large_excluded(self):
        # 1500 * 1.21 = 1815 → above 1500 * 1.20 = 1800
        result = self._estimate_with([_make_comp(sqft=1815)])
        assert result.comp_count == 0

    def test_sqft_at_boundary_included(self):
        # exactly ±20% should pass
        result = self._estimate_with([_make_comp(sqft=1200), _make_comp(sqft=1800)])
        assert result.comp_count == 2

    def test_old_sale_excluded(self):
        result = self._estimate_with([_make_comp(days_ago=366)])
        assert result.comp_count == 0

    def test_sale_within_365_days_included(self):
        result = self._estimate_with([_make_comp(days_ago=365)])
        assert result.comp_count == 1

    def test_valid_comp_passes_all_filters(self):
        result = self._estimate_with([_make_comp()])
        assert result.comp_count == 1


# ── confidence tiers ──────────────────────────────────────────────────────────

class TestConfidenceTiers:
    def _estimate_with_n(self, n):
        comps = [_make_comp() for _ in range(n)]
        with patch("services.arv_engine.arv._get_comps", return_value=comps):
            return calculator.estimate(_SUBJECT)

    def test_one_comp_confidence_50(self):
        assert self._estimate_with_n(1).arv_confidence == pytest.approx(50.0)

    def test_two_comps_confidence_50(self):
        assert self._estimate_with_n(2).arv_confidence == pytest.approx(50.0)

    def test_three_comps_confidence_70(self):
        assert self._estimate_with_n(3).arv_confidence == pytest.approx(70.0)

    def test_four_comps_confidence_70(self):
        assert self._estimate_with_n(4).arv_confidence == pytest.approx(70.0)

    def test_five_comps_confidence_90(self):
        assert self._estimate_with_n(5).arv_confidence == pytest.approx(90.0)

    def test_ten_comps_confidence_90(self):
        assert self._estimate_with_n(10).arv_confidence == pytest.approx(90.0)


# ── ARV math ──────────────────────────────────────────────────────────────────

class TestARVMath:
    def test_single_comp_arv_equals_price(self):
        # 1 comp at $300/sqft × 1500 sqft = $450,000
        comp = _make_comp(sale_price=450_000, sqft=1500)
        with patch("services.arv_engine.arv._get_comps", return_value=[comp]):
            result = calculator.estimate(_SUBJECT)
        assert result.arv == pytest.approx(450_000.0)

    def test_two_equal_distance_comps_average(self):
        # Both at same distance → simple average ppsf
        # comp1: $300k / 1500sqft = $200/sqft
        # comp2: $450k / 1500sqft = $300/sqft
        # avg = $250/sqft → ARV = $375k
        comps = [
            _make_comp(sale_price=300_000, sqft=1500, distance_miles=1.0),
            _make_comp(sale_price=450_000, sqft=1500, distance_miles=1.0),
        ]
        with patch("services.arv_engine.arv._get_comps", return_value=comps):
            result = calculator.estimate(_SUBJECT)
        assert result.arv == pytest.approx(375_000.0, rel=1e-4)

    def test_closer_comp_weighted_more(self):
        # comp_near at $200/sqft, distance 0.1 miles → weight = 1/(0.1+0.1) = 5
        # comp_far  at $400/sqft, distance 9.9 miles → weight = 1/(9.9+0.1) = 0.1
        # weighted ppsf = (5*200 + 0.1*400) / 5.1 ≈ 203.92
        # ARV ≈ 203.92 * 1500 ≈ 305,882
        comp_near = _make_comp(sale_price=300_000, sqft=1500, distance_miles=0.1)
        comp_far  = _make_comp(sale_price=600_000, sqft=1500, distance_miles=9.9)
        with patch("services.arv_engine.arv._get_comps", return_value=[comp_near, comp_far]):
            result = calculator.estimate(_SUBJECT)
        # near-comp should dominate → ARV closer to $300k than $600k
        assert result.arv < 400_000
        assert result.arv > 300_000
