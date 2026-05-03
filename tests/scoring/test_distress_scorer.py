"""
Unit tests for the distress score engine.

Covers:
  - Individual component calculations (foreclosure, tax, preforeclosure, probate)
  - Weighted composite score
  - Edge cases (zero signals, missing fields, clamping to [0, 100])
  - ForeclosureStage enum mapping
  - DistressScoreResult fields
"""

from datetime import date

import pytest

from services.distress_score.scorer import (
    DistressScorer,
    DistressSignals,
    _STAGE_SCORES,
    _TAX_PTS_PER_YEAR,
    _WEIGHTS,
)
from ingestion.shared.models import ForeclosureStage


scorer = DistressScorer()


# ── foreclosure component ──────────────────────────────────────────────────────

class TestForeclosureComponent:
    def test_nod_score(self):
        result = scorer.score(DistressSignals(foreclosure_stage=ForeclosureStage.NOD.value))
        assert result.foreclosure_component == _STAGE_SCORES[ForeclosureStage.NOD.value]

    def test_nts_score(self):
        result = scorer.score(DistressSignals(foreclosure_stage=ForeclosureStage.NTS.value))
        assert result.foreclosure_component == _STAGE_SCORES[ForeclosureStage.NTS.value]

    def test_auction_score(self):
        result = scorer.score(DistressSignals(foreclosure_stage=ForeclosureStage.auction.value))
        assert result.foreclosure_component == _STAGE_SCORES[ForeclosureStage.auction.value]

    def test_reo_score(self):
        result = scorer.score(DistressSignals(foreclosure_stage=ForeclosureStage.REO.value))
        assert result.foreclosure_component == _STAGE_SCORES[ForeclosureStage.REO.value]

    def test_no_stage_returns_zero(self):
        result = scorer.score(DistressSignals())
        assert result.foreclosure_component == 0.0

    def test_unknown_stage_returns_zero(self):
        result = scorer.score(DistressSignals(foreclosure_stage="UNKNOWN"))
        assert result.foreclosure_component == 0.0


# ── tax delinquency component ──────────────────────────────────────────────────

class TestTaxComponent:
    @pytest.mark.parametrize("years,expected", [
        (1,  15.0),
        (3,  45.0),
        (5,  75.0),
        (7, 100.0),   # capped
        (10, 100.0),  # capped
        (0,   0.0),
    ])
    def test_tax_component_values(self, years, expected):
        result = scorer.score(DistressSignals(years_delinquent=years))
        assert result.tax_component == expected

    def test_no_tax_returns_zero(self):
        result = scorer.score(DistressSignals())
        assert result.tax_component == 0.0

    def test_negative_years_returns_zero(self):
        result = scorer.score(DistressSignals(years_delinquent=-1))
        assert result.tax_component == 0.0


# ── pre-foreclosure component ──────────────────────────────────────────────────

class TestPreforeclosureComponent:
    def test_filed_today_returns_100(self):
        today = date.today()
        result = scorer.score(DistressSignals(lp_filing_date=today, as_of=today))
        assert result.preforeclosure_component == 100.0

    def test_filed_150_days_ago_returns_50(self):
        from datetime import timedelta
        ref = date(2025, 6, 1)
        filing = ref - timedelta(days=150)
        result = scorer.score(DistressSignals(lp_filing_date=filing, as_of=ref))
        assert result.preforeclosure_component == 50.0

    def test_filed_300_days_ago_returns_zero(self):
        from datetime import timedelta
        ref = date(2025, 6, 1)
        filing = ref - timedelta(days=300)
        result = scorer.score(DistressSignals(lp_filing_date=filing, as_of=ref))
        assert result.preforeclosure_component == 0.0

    def test_filed_400_days_ago_clamped_zero(self):
        from datetime import timedelta
        ref = date(2025, 6, 1)
        filing = ref - timedelta(days=400)
        result = scorer.score(DistressSignals(lp_filing_date=filing, as_of=ref))
        assert result.preforeclosure_component == 0.0

    def test_no_lp_returns_zero(self):
        result = scorer.score(DistressSignals())
        assert result.preforeclosure_component == 0.0


# ── probate component ──────────────────────────────────────────────────────────

class TestProbateComponent:
    def test_active_probate_returns_100(self):
        result = scorer.score(DistressSignals(has_active_probate=True))
        assert result.probate_component == 100.0

    def test_no_probate_returns_zero(self):
        result = scorer.score(DistressSignals(has_active_probate=False))
        assert result.probate_component == 0.0


# ── composite score ────────────────────────────────────────────────────────────

class TestCompositeScore:
    def test_all_zero_signals_returns_zero(self):
        result = scorer.score(DistressSignals())
        assert result.score == 0.0

    def test_all_max_signals_returns_100(self):
        today = date.today()
        result = scorer.score(DistressSignals(
            foreclosure_stage=ForeclosureStage.auction.value,
            years_delinquent=10,
            has_active_probate=True,
            lp_filing_date=today,
            as_of=today,
        ))
        assert result.score == 100.0

    def test_nts_only_weighted_correctly(self):
        result = scorer.score(DistressSignals(foreclosure_stage=ForeclosureStage.NTS.value))
        expected = round(75.0 * _WEIGHTS["foreclosure"], 2)
        assert result.score == expected

    def test_score_clamped_to_100(self):
        # Even with inflated inputs the score must not exceed 100
        result = scorer.score(DistressSignals(
            foreclosure_stage=ForeclosureStage.auction.value,
            years_delinquent=999,
            has_active_probate=True,
            lp_filing_date=date.today(),
            as_of=date.today(),
        ))
        assert result.score <= 100.0

    def test_score_two_decimal_precision(self):
        result = scorer.score(DistressSignals(years_delinquent=1))
        assert result.score == round(result.score, 2)

    def test_result_version_default(self):
        result = scorer.score(DistressSignals())
        assert result.score_version == "1.0"
