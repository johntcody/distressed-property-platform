"""
Pure-Python equity and amortization logic — no framework dependency.

Amortization model
------------------
Given an original loan at a fixed annual rate, compute the outstanding
principal balance after `months_elapsed` payments using the standard
present-value formula:

    B = P × [(1+r)^n − (1+r)^k] / [(1+r)^n − 1]

where:
    P = original principal
    r = monthly interest rate (annual_rate / 12)
    n = total term in months
    k = months already elapsed

If r == 0 (interest-free) the balance falls back to straight-line
amortization: B = P × (n − k) / n.

Equity formula
--------------
    equity_amount = AVM − estimated_loan_balance − tax_owed
    equity_pct    = equity_amount / AVM × 100   (None when AVM == 0)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ── constants ─────────────────────────────────────────────────────────────────

_DEFAULT_ANNUAL_RATE: float = 0.07   # 7 % — reasonable TX market default
_DEFAULT_TERM_MONTHS: int  = 360     # 30-year mortgage


# ── data classes ──────────────────────────────────────────────────────────────

@dataclass
class AmortizationInputs:
    original_loan_amount: float
    annual_rate: float = _DEFAULT_ANNUAL_RATE
    term_months: int   = _DEFAULT_TERM_MONTHS
    months_elapsed: int = 0


@dataclass
class EquityInputs:
    avm: float
    original_loan_amount: Optional[float] = None
    annual_rate: float  = _DEFAULT_ANNUAL_RATE
    term_months: int    = _DEFAULT_TERM_MONTHS
    months_elapsed: int = 0
    tax_owed: float     = 0.0


@dataclass
class EquityResult:
    avm: float
    estimated_loan_balance: float
    tax_owed: float
    equity_amount: float
    equity_pct: Optional[float]      # None when AVM == 0
    calculator_version: str = "1.0"


# ── calculator ────────────────────────────────────────────────────────────────

class EquityCalculator:

    def estimate_loan_balance(self, inputs: AmortizationInputs) -> float:
        """Return outstanding principal after `months_elapsed` payments."""
        P = inputs.original_loan_amount
        r = inputs.annual_rate / 12
        n = inputs.term_months
        k = min(inputs.months_elapsed, n)  # can't be more paid off than the term

        if P <= 0:
            return 0.0

        if k >= n:
            return 0.0  # fully paid off

        if r == 0:
            return P * (n - k) / n

        factor = (1 + r) ** n
        return P * (factor - (1 + r) ** k) / (factor - 1)

    def calculate(self, inputs: EquityInputs) -> EquityResult:
        """Compute equity amount and percentage."""
        avm = inputs.avm

        if inputs.original_loan_amount is not None and inputs.original_loan_amount > 0:
            loan_balance = self.estimate_loan_balance(
                AmortizationInputs(
                    original_loan_amount=inputs.original_loan_amount,
                    annual_rate=inputs.annual_rate,
                    term_months=inputs.term_months,
                    months_elapsed=inputs.months_elapsed,
                )
            )
        else:
            loan_balance = 0.0

        tax_owed    = max(inputs.tax_owed, 0.0)
        equity_amt  = avm - loan_balance - tax_owed
        equity_pct  = round(equity_amt / avm * 100, 2) if avm > 0 else None

        return EquityResult(
            avm=round(avm, 2),
            estimated_loan_balance=round(loan_balance, 2),
            tax_owed=round(tax_owed, 2),
            equity_amount=round(equity_amt, 2),
            equity_pct=equity_pct,
        )
