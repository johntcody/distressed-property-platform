"""
Unit tests for the MAO calculator.

Covers:
  - Basic formula: MAO = (ARV × discount_pct/100) − rehab − holding − closing
  - Default discount_pct is 70.0
  - Default holding_costs and closing_costs are 0.0
  - Discount_pct=100 yields ARV − costs
  - MAO can be negative (underwater deal)
  - arv <= 0 raises ValueError
  - discount_pct <= 0 raises ValueError
  - discount_pct > 100 raises ValueError
  - rehab_cost < 0 raises ValueError
  - holding_costs < 0 raises ValueError
  - closing_costs < 0 raises ValueError
  - Result echoes all inputs
  - mao_version default is "1.0"
"""

import pytest

from services.mao_engine.calculator import MAOCalculator, MAOInputs

calc = MAOCalculator()


# ── formula correctness ───────────────────────────────────────────────────────

class TestFormula:
    def test_basic_70_percent_rule_no_costs(self):
        result = calc.calculate(MAOInputs(arv=200_000, rehab_cost=30_000))
        # (200000 * 0.70) - 30000 = 110000
        assert result.mao == pytest.approx(110_000.0)

    def test_holding_and_closing_costs_reduce_mao(self):
        result = calc.calculate(MAOInputs(
            arv=200_000, rehab_cost=30_000,
            holding_costs=5_000, closing_costs=3_000
        ))
        # 140000 - 30000 - 5000 - 3000 = 102000
        assert result.mao == pytest.approx(102_000.0)

    def test_discount_pct_applied_correctly(self):
        result = calc.calculate(MAOInputs(arv=300_000, rehab_cost=0, discount_pct=65.0))
        assert result.mao == pytest.approx(195_000.0)

    def test_discount_pct_100_yields_arv_minus_costs(self):
        result = calc.calculate(MAOInputs(arv=100_000, rehab_cost=10_000, discount_pct=100.0))
        assert result.mao == pytest.approx(90_000.0)

    def test_mao_can_be_negative(self):
        # Rehab exceeds discounted ARV
        result = calc.calculate(MAOInputs(arv=100_000, rehab_cost=80_000, discount_pct=70.0))
        # 70000 - 80000 = -10000
        assert result.mao == pytest.approx(-10_000.0)

    def test_zero_rehab_cost(self):
        result = calc.calculate(MAOInputs(arv=200_000, rehab_cost=0))
        assert result.mao == pytest.approx(140_000.0)

    def test_fractional_discount_pct(self):
        result = calc.calculate(MAOInputs(arv=150_000, rehab_cost=0, discount_pct=72.5))
        assert result.mao == pytest.approx(108_750.0)


# ── defaults ──────────────────────────────────────────────────────────────────

class TestDefaults:
    def test_default_discount_pct_is_70(self):
        result = calc.calculate(MAOInputs(arv=100_000, rehab_cost=0))
        assert result.discount_pct == 70.0

    def test_default_holding_costs_is_zero(self):
        result = calc.calculate(MAOInputs(arv=100_000, rehab_cost=0))
        assert result.holding_costs == 0.0

    def test_default_closing_costs_is_zero(self):
        result = calc.calculate(MAOInputs(arv=100_000, rehab_cost=0))
        assert result.closing_costs == 0.0

    def test_mao_version_default(self):
        result = calc.calculate(MAOInputs(arv=100_000, rehab_cost=0))
        assert result.mao_version == "1.0"


# ── result echoes inputs ──────────────────────────────────────────────────────

class TestResultEchoes:
    def test_arv_echoed(self):
        result = calc.calculate(MAOInputs(arv=250_000, rehab_cost=0))
        assert result.arv == 250_000.0

    def test_discount_pct_echoed(self):
        result = calc.calculate(MAOInputs(arv=100_000, rehab_cost=0, discount_pct=65.0))
        assert result.discount_pct == 65.0

    def test_rehab_cost_echoed(self):
        result = calc.calculate(MAOInputs(arv=100_000, rehab_cost=15_000))
        assert result.rehab_cost == 15_000.0

    def test_holding_costs_echoed(self):
        result = calc.calculate(MAOInputs(arv=100_000, rehab_cost=0, holding_costs=4_000))
        assert result.holding_costs == 4_000.0

    def test_closing_costs_echoed(self):
        result = calc.calculate(MAOInputs(arv=100_000, rehab_cost=0, closing_costs=2_500))
        assert result.closing_costs == 2_500.0


# ── validation ────────────────────────────────────────────────────────────────

class TestValidation:
    def test_zero_arv_raises(self):
        with pytest.raises(ValueError, match="arv"):
            calc.calculate(MAOInputs(arv=0, rehab_cost=0))

    def test_negative_arv_raises(self):
        with pytest.raises(ValueError, match="arv"):
            calc.calculate(MAOInputs(arv=-1, rehab_cost=0))

    def test_zero_discount_pct_raises(self):
        with pytest.raises(ValueError, match="discount_pct"):
            calc.calculate(MAOInputs(arv=100_000, rehab_cost=0, discount_pct=0))

    def test_discount_pct_above_100_raises(self):
        with pytest.raises(ValueError, match="discount_pct"):
            calc.calculate(MAOInputs(arv=100_000, rehab_cost=0, discount_pct=101))

    def test_negative_rehab_raises(self):
        with pytest.raises(ValueError, match="rehab_cost"):
            calc.calculate(MAOInputs(arv=100_000, rehab_cost=-1))

    def test_negative_holding_costs_raises(self):
        with pytest.raises(ValueError, match="holding_costs"):
            calc.calculate(MAOInputs(arv=100_000, rehab_cost=0, holding_costs=-1))

    def test_negative_closing_costs_raises(self):
        with pytest.raises(ValueError, match="closing_costs"):
            calc.calculate(MAOInputs(arv=100_000, rehab_cost=0, closing_costs=-1))
