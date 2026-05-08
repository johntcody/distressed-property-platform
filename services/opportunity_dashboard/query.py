"""
Dynamic SQL builder for GET /opportunities.

Each filter is optional; only active filters are appended to the WHERE clause.
asyncpg uses positional parameters ($1, $2, …), so a counter tracks the next
available slot as clauses are added.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

_SORTABLE = {
    "distress_score": "s.distress_score",
    "equity_pct":     "s.equity_pct",
    "auction_date":   "e_latest.auction_date",
    "filing_date":    "e_latest.filing_date",
    "mao":            "a_latest.mao",
}

_BASE_QUERY = """\
SELECT
    p.id               AS property_id,
    p.address_norm     AS address,
    p.city,
    p.county,
    p.zip_code,
    p.sqft,
    p.bedrooms,
    p.bathrooms,
    p.year_built,
    p.owner_name,
    s.distress_score,
    s.equity_pct,
    s.equity_amount,
    s.avm,
    v_latest.arv,
    a_latest.mao,
    e_latest.event_type,
    e_latest.foreclosure_stage,
    e_latest.filing_date,
    e_latest.auction_date
FROM properties p
LEFT JOIN latest_property_scores s ON s.property_id = p.id
LEFT JOIN LATERAL (
    SELECT arv
    FROM   valuations
    WHERE  property_id = p.id AND arv_confidence IS NOT NULL
    ORDER  BY calculated_at DESC LIMIT 1
) v_latest ON TRUE
LEFT JOIN LATERAL (
    SELECT mao
    FROM   analysis
    WHERE  property_id = p.id
      AND  record_type  = 'mao'
      AND  mao          IS NOT NULL
    ORDER  BY calculated_at DESC LIMIT 1
) a_latest ON TRUE
LEFT JOIN LATERAL (
    SELECT event_type, foreclosure_stage, filing_date, auction_date
    FROM   events
    WHERE  property_id = p.id
    ORDER  BY filing_date DESC NULLS LAST LIMIT 1
) e_latest ON TRUE
"""

_COUNT_QUERY = """\
SELECT COUNT(*) AS total
FROM properties p
LEFT JOIN latest_property_scores s ON s.property_id = p.id
LEFT JOIN LATERAL (
    SELECT event_type, foreclosure_stage, filing_date, auction_date
    FROM   events
    WHERE  property_id = p.id
    ORDER  BY filing_date DESC NULLS LAST LIMIT 1
) e_latest ON TRUE
"""


@dataclass
class _Builder:
    clauses: list[str] = field(default_factory=list)
    params:  list      = field(default_factory=list)

    def add(self, clause: str, value) -> None:
        self.params.append(value)
        self.clauses.append(clause.replace("?", f"${len(self.params)}"))

    def where_sql(self) -> str:
        if not self.clauses:
            return ""
        return "WHERE " + "\n  AND ".join(self.clauses)


def build_query(
    *,
    county:              Optional[str],
    case_type:           Optional[str],
    min_distress_score:  Optional[float],
    min_equity_pct:      Optional[float],
    auction_date_before: Optional[date],
    sort_by:             str,
    sort_dir:            str,
    limit:               int,
    offset:              int,
) -> tuple[str, list, str, list]:
    """Return (data_sql, data_params, count_sql, count_params)."""
    b = _Builder()

    if county:
        b.add("p.county = ?", county)
    if case_type:
        b.add("e_latest.event_type::TEXT = ?", case_type)
    if min_distress_score is not None:
        b.add("s.distress_score >= ?", min_distress_score)
    if min_equity_pct is not None:
        b.add("s.equity_pct >= ?", min_equity_pct)
    if auction_date_before is not None:
        b.add("e_latest.auction_date <= ?", auction_date_before)

    where = b.where_sql()
    sort_col = _SORTABLE.get(sort_by, "s.distress_score")
    direction = "DESC" if sort_dir == "desc" else "ASC"
    nulls = "NULLS LAST" if sort_dir == "desc" else "NULLS FIRST"

    # Pagination params come after the filter params
    data_params = list(b.params) + [limit, offset]
    limit_n  = len(data_params) - 1
    offset_n = len(data_params)

    data_sql = (
        f"{_BASE_QUERY}\n{where}\n"
        f"ORDER BY {sort_col} {direction} {nulls}\n"
        f"LIMIT ${limit_n} OFFSET ${offset_n}"
    )

    count_sql    = f"{_COUNT_QUERY}\n{where}"
    count_params = list(b.params)

    return data_sql, data_params, count_sql, count_params
