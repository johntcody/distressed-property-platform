"""
Unit tests for the market scorer.

Covers:
  - Perfect inputs → score of 100
  - Worst inputs → score of 0
  - Missing signals default to 50 (neutral sub-score)
  - All signals missing → score of 50
  - Partial signals: only appreciation provided
  - Sub-score clamping (values beyond thresholds don't exceed 0 or 100)
  - Score precision (rounded to 2 decimal places)
  - score_version default
  - inputs_used echoed in result
"""

import pytest

from services.market_score.scorer import MarketInputs, MarketScorer

scorer = MarketScorer()


# ── boundary scores ───────────────────────────────────────────────────────────

class TestBoundaryScores:
    def test_perfect_inputs_score_100(self):
        result = scorer.score(MarketInputs(
            appreciation_rate=0.15,    # at APPRECIATION_MAX
            avg_days_on_market=0.0,    # instant sale
            rent_to_price_ratio=0.10,  # at YIELD_MAX
        ))
        assert result.market_score == pytest.approx(100.0)

    def test_worst_inputs_score_0(self):
        result = scorer.score(MarketInputs(
            appreciation_rate=0.0,
            avg_days_on_market=120.0,  # at DOM_MAX
            rent_to_price_ratio=0.0,
        ))
        assert result.market_score == pytest.approx(0.0)

    def test_beyond_max_appreciation_clamped_to_100(self):
        result = scorer.score(MarketInputs(appreciation_rate=0.50))
        assert result.appreciation_score == pytest.approx(100.0)

    def test_dom_beyond_max_clamped_to_0(self):
        result = scorer.score(MarketInputs(avg_days_on_market=300))
        assert result.liquidity_score == pytest.approx(0.0)

    def test_negative_appreciation_clamped_to_0(self):
        result = scorer.score(MarketInputs(appreciation_rate=-0.10))
        assert result.appreciation_score == pytest.approx(0.0)


# ── missing signals ───────────────────────────────────────────────────────────

class TestMissingSignals:
    def test_all_missing_score_is_50(self):
        result = scorer.score(MarketInputs())
        assert result.market_score == pytest.approx(50.0)
        assert result.appreciation_score == pytest.approx(50.0)
        assert result.liquidity_score == pytest.approx(50.0)
        assert result.yield_score == pytest.approx(50.0)

    def test_only_appreciation_provided(self):
        # appreciation=100%, others neutral(50) → (100 + 50 + 50) / 3
        result = scorer.score(MarketInputs(appreciation_rate=0.15))
        assert result.market_score == pytest.approx((100 + 50 + 50) / 3, rel=1e-4)
        assert result.appreciation_score == pytest.approx(100.0)
        assert result.liquidity_score == pytest.approx(50.0)
        assert result.yield_score == pytest.approx(50.0)

    def test_only_dom_provided(self):
        # 60 days → liquidity = (1 - 60/120) * 100 = 50
        result = scorer.score(MarketInputs(avg_days_on_market=60))
        assert result.liquidity_score == pytest.approx(50.0)
        assert result.market_score == pytest.approx(50.0)

    def test_only_yield_provided(self):
        # 5% yield → yield_score = (0.05 / 0.10) * 100 = 50
        result = scorer.score(MarketInputs(rent_to_price_ratio=0.05))
        assert result.yield_score == pytest.approx(50.0)


# ── sub-score math ────────────────────────────────────────────────────────────

class TestSubScoreMath:
    def test_appreciation_midpoint(self):
        # 7.5% appreciation = 50% of 15% max
        result = scorer.score(MarketInputs(appreciation_rate=0.075))
        assert result.appreciation_score == pytest.approx(50.0)

    def test_liquidity_midpoint(self):
        result = scorer.score(MarketInputs(avg_days_on_market=60))
        assert result.liquidity_score == pytest.approx(50.0)

    def test_yield_midpoint(self):
        result = scorer.score(MarketInputs(rent_to_price_ratio=0.05))
        assert result.yield_score == pytest.approx(50.0)

    def test_market_score_is_average_of_three(self):
        result = scorer.score(MarketInputs(
            appreciation_rate=0.15,   # 100
            avg_days_on_market=60,    # 50
            rent_to_price_ratio=0.0,  # 0
        ))
        assert result.market_score == pytest.approx((100 + 50 + 0) / 3, rel=1e-4)


# ── result metadata ───────────────────────────────────────────────────────────

class TestResultMetadata:
    def test_score_version_default(self):
        result = scorer.score(MarketInputs())
        assert result.score_version == "1.0"

    def test_market_score_rounded_to_two_decimals(self):
        result = scorer.score(MarketInputs(
            appreciation_rate=0.10,
            avg_days_on_market=45,
            rent_to_price_ratio=0.08,
        ))
        assert result.market_score == round(result.market_score, 2)

    def test_inputs_used_echoed(self):
        result = scorer.score(MarketInputs(
            appreciation_rate=0.06,
            avg_days_on_market=30,
            rent_to_price_ratio=0.07,
        ))
        assert result.inputs_used["appreciation_rate"] == pytest.approx(0.06)
        assert result.inputs_used["avg_days_on_market"] == pytest.approx(30)
        assert result.inputs_used["rent_to_price_ratio"] == pytest.approx(0.07)

    def test_missing_inputs_echoed_as_none(self):
        result = scorer.score(MarketInputs())
        assert result.inputs_used["appreciation_rate"] is None
        assert result.inputs_used["avg_days_on_market"] is None
        assert result.inputs_used["rent_to_price_ratio"] is None

    def test_zip_code_passed_through(self):
        result = scorer.score(MarketInputs(zip_code="78701"))
        assert result.zip_code == "78701"
