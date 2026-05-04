"""
Unit tests for the equity calculator.

Covers:
  - Amortization model (standard, interest-free, fully elapsed, zero principal)
  - Equity calculation (with/without loan, with/without tax, negative equity)
  - Edge cases (AVM == 0, no loan data)
  - equity_pct precision
"""

import math
import pytest

from services.equity_engine.calculator import (
    AmortizationInputs,
    EquityCalculator,
    EquityInputs,
    EquityResult,
    _DEFAULT_ANNUAL_RATE,
    _DEFAULT_TERM_MONTHS,
)

calc = EquityCalculator()


# ── amortization ──────────────────────────────────────────────────────────────

class TestAmortization:
    def test_no_payments_balance_equals_principal(self):
        bal = calc.estimate_loan_balance(
            AmortizationInputs(original_loan_amount=200_000, months_elapsed=0)
        )
        assert bal == pytest.approx(200_000, rel=1e-4)

    def test_fully_elapsed_returns_zero(self):
        bal = calc.estimate_loan_balance(
            AmortizationInputs(
                original_loan_amount=200_000,
                months_elapsed=360,
                term_months=360,
            )
        )
        assert bal == 0.0

    def test_past_term_clamped_to_zero(self):
        bal = calc.estimate_loan_balance(
            AmortizationInputs(
                original_loan_amount=200_000,
                months_elapsed=400,
                term_months=360,
            )
        )
        assert bal == 0.0

    def test_zero_principal_returns_zero(self):
        bal = calc.estimate_loan_balance(
            AmortizationInputs(original_loan_amount=0, months_elapsed=60)
        )
        assert bal == 0.0

    def test_negative_principal_returns_zero(self):
        bal = calc.estimate_loan_balance(
            AmortizationInputs(original_loan_amount=-5000, months_elapsed=0)
        )
        assert bal == 0.0

    def test_interest_free_straight_line(self):
        # 0% rate, 120-month term, 60 months elapsed → 50% remaining
        bal = calc.estimate_loan_balance(
            AmortizationInputs(
                original_loan_amount=100_000,
                annual_rate=0.0,
                term_months=120,
                months_elapsed=60,
            )
        )
        assert bal == pytest.approx(50_000, rel=1e-6)

    def test_standard_mortgage_midpoint_less_than_half(self):
        # On a standard amortizing loan, mid-point balance > 50% of original
        # because early payments are mostly interest.
        bal = calc.estimate_loan_balance(
            AmortizationInputs(
                original_loan_amount=300_000,
                annual_rate=0.07,
                term_months=360,
                months_elapsed=180,
            )
        )
        # Balance should be positive and greater than half the original principal
        assert bal > 150_000

    def test_balance_decreases_over_time(self):
        kwargs = dict(original_loan_amount=200_000, annual_rate=0.065, term_months=360)
        b1 = calc.estimate_loan_balance(AmortizationInputs(months_elapsed=12, **kwargs))
        b2 = calc.estimate_loan_balance(AmortizationInputs(months_elapsed=120, **kwargs))
        b3 = calc.estimate_loan_balance(AmortizationInputs(months_elapsed=300, **kwargs))
        assert b1 > b2 > b3 > 0


# ── equity calculation ────────────────────────────────────────────────────────

class TestEquityCalculation:
    def test_no_loan_no_tax_equity_equals_avm(self):
        result = calc.calculate(EquityInputs(avm=300_000))
        assert result.equity_amount == pytest.approx(300_000, rel=1e-6)
        assert result.equity_pct == pytest.approx(100.0, rel=1e-4)

    def test_full_loan_no_payments_zero_equity(self):
        result = calc.calculate(
            EquityInputs(avm=200_000, original_loan_amount=200_000, months_elapsed=0)
        )
        # equity_amount ≈ 0 (tiny residual possible due to amortization math)
        assert result.equity_amount == pytest.approx(0.0, abs=1.0)

    def test_tax_owed_reduces_equity(self):
        result_no_tax = calc.calculate(EquityInputs(avm=300_000))
        result_with_tax = calc.calculate(EquityInputs(avm=300_000, tax_owed=10_000))
        assert result_with_tax.equity_amount == pytest.approx(
            result_no_tax.equity_amount - 10_000, rel=1e-6
        )

    def test_negative_equity_allowed(self):
        result = calc.calculate(
            EquityInputs(avm=100_000, original_loan_amount=150_000, months_elapsed=0)
        )
        assert result.equity_amount < 0
        assert result.equity_pct < 0

    def test_avm_zero_equity_pct_is_none(self):
        result = calc.calculate(EquityInputs(avm=0))
        assert result.equity_pct is None

    def test_avm_zero_equity_amount_subtracts_tax(self):
        result = calc.calculate(EquityInputs(avm=0, tax_owed=5_000))
        assert result.equity_amount == pytest.approx(-5_000, rel=1e-6)

    def test_negative_tax_clamped_to_zero(self):
        result_clean = calc.calculate(EquityInputs(avm=200_000))
        result_neg   = calc.calculate(EquityInputs(avm=200_000, tax_owed=-999))
        assert result_neg.equity_amount == result_clean.equity_amount

    def test_equity_pct_precision_two_decimals(self):
        result = calc.calculate(EquityInputs(avm=300_000, tax_owed=10_000))
        assert result.equity_pct == round(result.equity_pct, 2)

    def test_result_fields_rounded_to_cents(self):
        result = calc.calculate(
            EquityInputs(
                avm=312_567.891,
                original_loan_amount=187_234.567,
                months_elapsed=24,
                tax_owed=3_456.789,
            )
        )
        for field in (result.avm, result.estimated_loan_balance, result.tax_owed, result.equity_amount):
            assert field == round(field, 2)

    def test_calculator_version_default(self):
        result = calc.calculate(EquityInputs(avm=100_000))
        assert result.calculator_version == "1.0"

    def test_partial_paydown_reduces_balance(self):
        result_early = calc.calculate(
            EquityInputs(avm=400_000, original_loan_amount=300_000, months_elapsed=12)
        )
        result_late = calc.calculate(
            EquityInputs(avm=400_000, original_loan_amount=300_000, months_elapsed=300)
        )
        assert result_late.equity_amount > result_early.equity_amount
