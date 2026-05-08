"""
Unit tests for the rehab cost estimator.

Covers:
  - Light template: correct line items, total, cost_per_sqft
  - Medium template: correct line items, total, cost_per_sqft
  - Heavy template: correct line items, total, cost_per_sqft
  - Caller override replaces individual line item
  - New line item added via overrides
  - total_cost = sum of all line_items
  - cost_per_sqft = total_cost / sqft
  - Invalid rehab_level raises ValueError
  - sqft <= 0 raises ValueError
  - rehab_version default
"""

import pytest

from services.rehab_engine.estimator import RehabEstimator, RehabInputs, _TEMPLATES

estimator = RehabEstimator()


# ── helpers ───────────────────────────────────────────────────────────────────

def _expected_total(level: str, sqft: float, overrides: dict = None) -> float:
    template = dict(_TEMPLATES[level])
    if overrides:
        template.update(overrides)
    return round(sum(rate * sqft for rate in template.values()), 2)


# ── template outputs ──────────────────────────────────────────────────────────

class TestTemplates:
    def test_light_total_matches_template(self):
        result = estimator.estimate(RehabInputs(sqft=1000, rehab_level="light"))
        assert result.total_cost == pytest.approx(_expected_total("light", 1000))

    def test_medium_total_matches_template(self):
        result = estimator.estimate(RehabInputs(sqft=1500, rehab_level="medium"))
        assert result.total_cost == pytest.approx(_expected_total("medium", 1500))

    def test_heavy_total_matches_template(self):
        result = estimator.estimate(RehabInputs(sqft=2000, rehab_level="heavy"))
        assert result.total_cost == pytest.approx(_expected_total("heavy", 2000))

    def test_light_has_fewer_line_items_than_heavy(self):
        light = estimator.estimate(RehabInputs(sqft=1000, rehab_level="light"))
        heavy = estimator.estimate(RehabInputs(sqft=1000, rehab_level="heavy"))
        assert len(light.line_items) < len(heavy.line_items)

    def test_heavy_includes_roof_line_item(self):
        result = estimator.estimate(RehabInputs(sqft=1000, rehab_level="heavy"))
        assert "roof" in result.line_items

    def test_light_does_not_include_roof(self):
        result = estimator.estimate(RehabInputs(sqft=1000, rehab_level="light"))
        assert "roof" not in result.line_items


# ── math correctness ─────────────────────────────────────────────────────────

class TestMath:
    def test_total_cost_equals_sum_of_line_items(self):
        result = estimator.estimate(RehabInputs(sqft=1200, rehab_level="medium"))
        assert result.total_cost == pytest.approx(sum(result.line_items.values()), rel=1e-6)

    def test_cost_per_sqft_equals_total_divided_by_sqft(self):
        result = estimator.estimate(RehabInputs(sqft=1500, rehab_level="heavy"))
        assert result.cost_per_sqft == pytest.approx(result.total_cost / 1500, rel=1e-6)

    def test_line_item_equals_rate_times_sqft(self):
        # paint rate for medium = 4.00/sqft
        result = estimator.estimate(RehabInputs(sqft=1000, rehab_level="medium"))
        assert result.line_items["paint"] == pytest.approx(4.00 * 1000)

    def test_total_scales_linearly_with_sqft(self):
        r1 = estimator.estimate(RehabInputs(sqft=1000, rehab_level="medium"))
        r2 = estimator.estimate(RehabInputs(sqft=2000, rehab_level="medium"))
        assert r2.total_cost == pytest.approx(r1.total_cost * 2, rel=1e-6)

    def test_default_level_is_medium(self):
        result = estimator.estimate(RehabInputs(sqft=1000))
        assert result.rehab_level == "medium"


# ── caller overrides ─────────────────────────────────────────────────────────

class TestOverrides:
    def test_override_replaces_template_line_item(self):
        # hvac default for medium = 5.00/sqft; override to 10.00
        result = estimator.estimate(RehabInputs(
            sqft=1000, rehab_level="medium", overrides={"hvac": 10.00}
        ))
        assert result.line_items["hvac"] == pytest.approx(10_000.0)

    def test_override_affects_total(self):
        base = estimator.estimate(RehabInputs(sqft=1000, rehab_level="medium"))
        overridden = estimator.estimate(RehabInputs(
            sqft=1000, rehab_level="medium", overrides={"hvac": 10.00}
        ))
        # hvac delta = (10 - 5) * 1000 = 5000
        assert overridden.total_cost == pytest.approx(base.total_cost + 5_000.0)

    def test_new_line_item_added_via_override(self):
        result = estimator.estimate(RehabInputs(
            sqft=1000, rehab_level="light", overrides={"pool": 20.00}
        ))
        assert "pool" in result.line_items
        assert result.line_items["pool"] == pytest.approx(20_000.0)

    def test_zero_override_sets_item_to_zero(self):
        result = estimator.estimate(RehabInputs(
            sqft=1000, rehab_level="medium", overrides={"hvac": 0.0}
        ))
        assert result.line_items["hvac"] == pytest.approx(0.0)


# ── validation ────────────────────────────────────────────────────────────────

class TestValidation:
    def test_invalid_level_raises(self):
        with pytest.raises(ValueError, match="rehab_level"):
            estimator.estimate(RehabInputs(sqft=1000, rehab_level="extreme"))

    def test_zero_sqft_raises(self):
        with pytest.raises(ValueError, match="sqft"):
            estimator.estimate(RehabInputs(sqft=0, rehab_level="light"))

    def test_negative_sqft_raises(self):
        with pytest.raises(ValueError, match="sqft"):
            estimator.estimate(RehabInputs(sqft=-500, rehab_level="light"))


# ── metadata ─────────────────────────────────────────────────────────────────

class TestMetadata:
    def test_rehab_version_default(self):
        result = estimator.estimate(RehabInputs(sqft=1000))
        assert result.rehab_version == "1.0"

    def test_rehab_level_echoed_in_result(self):
        result = estimator.estimate(RehabInputs(sqft=1000, rehab_level="heavy"))
        assert result.rehab_level == "heavy"

    def test_sqft_echoed_in_result(self):
        result = estimator.estimate(RehabInputs(sqft=1750))
        assert result.sqft == 1750.0
