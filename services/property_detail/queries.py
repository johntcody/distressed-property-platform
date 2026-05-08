"""Static SQL queries for the Property Detail API.

All queries accept a single parameter: $1 = property_id (UUID).
"""

PROPERTY_DETAIL_SQL = """\
SELECT
    p.id                AS property_id,
    p.apn,
    p.address_raw,
    p.address_norm,
    p.city,
    p.county,
    p.state,
    p.zip_code,
    p.legal_description,
    p.owner_name,
    p.sqft,
    p.bedrooms,
    p.bathrooms,
    p.year_built,
    p.land_value,
    p.improvement_value,
    p.total_cad_value,
    p.created_at,
    p.updated_at,
    s.distress_score,
    s.equity_pct,
    s.equity_amount,
    s.avm,
    s.market_score,
    s.estimated_liens,
    s.tax_owed,
    s.calculated_at     AS score_calculated_at
FROM properties p
LEFT JOIN latest_property_scores s ON s.property_id = p.id
WHERE p.id = $1
"""

EVENTS_SQL = """\
SELECT
    id               AS event_id,
    event_type::TEXT AS event_type,
    county,
    filing_date,
    auction_date,
    foreclosure_stage::TEXT AS foreclosure_stage,
    borrower_name,
    lender_name,
    trustee_name,
    loan_amount,
    tax_amount_owed,
    years_delinquent,
    case_number,
    source_url,
    created_at
FROM events
WHERE property_id = $1
ORDER BY filing_date DESC NULLS LAST, created_at DESC
"""

ANALYSIS_SQL = """\
SELECT
    a.id                AS analysis_id,
    a.record_type,
    a.rehab_level::TEXT AS rehab_level,
    a.rehab_cost,
    a.rehab_cost_sqft,
    a.arv_used,
    a.discount_pct,
    a.holding_costs,
    a.closing_costs,
    a.mao,
    a.mao_version,
    a.notes,
    a.calculated_at,
    v.arv               AS valuation_arv,
    v.arv_confidence,
    v.comp_count,
    v.method,
    v.provider
FROM analysis a
LEFT JOIN valuations v ON v.id = a.valuation_id
WHERE a.property_id = $1
ORDER BY a.calculated_at DESC
"""

VALUATIONS_SQL = """\
SELECT
    v.id              AS valuation_id,
    v.avm,
    v.arv,
    v.arv_confidence,
    v.comp_count,
    v.method,
    v.provider,
    v.confidence_score,
    v.valuation_date,
    v.arv_version,
    v.calculated_at
FROM valuations v
WHERE v.property_id = $1
ORDER BY v.calculated_at DESC
"""

EQUITY_SQL = """\
SELECT equity_pct, equity_amount, estimated_liens, tax_owed
FROM latest_property_scores
WHERE property_id = $1
"""
