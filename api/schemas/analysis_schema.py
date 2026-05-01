"""Analysis result schema — aggregated scoring and deal analysis output."""

from pydantic import BaseModel
from typing import Optional


class AnalysisResult(BaseModel):
    property_id: str
    distress_score: float
    equity_amount: Optional[float] = None
    equity_pct: Optional[float] = None
    arv: Optional[float] = None
    rehab_cost: Optional[float] = None
    mao: Optional[float] = None
    market_score: Optional[float] = None
    # TODO: add confidence intervals and data freshness timestamps
