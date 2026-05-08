"""
Unit tests for services.property_detail.queries.

Verifies that each SQL string:
  - Targets the correct table / view
  - Uses $1 as the sole positional parameter
  - Projects the expected columns
  - Applies the expected ORDER BY
  - Does not accidentally reference another endpoint's tables
"""

import pytest

from services.property_detail.queries import (
    ANALYSIS_SQL,
    EQUITY_SQL,
    EVENTS_SQL,
    PROPERTY_DETAIL_SQL,
    PROPERTY_EXISTS_SQL,
    VALUATIONS_SQL,
)


# ── PROPERTY_DETAIL_SQL ───────────────────────────────────────────────────────

class TestPropertyDetailSQL:
    def test_selects_from_properties(self):
        assert "FROM properties p" in PROPERTY_DETAIL_SQL

    def test_joins_latest_scores(self):
        assert "latest_property_scores" in PROPERTY_DETAIL_SQL

    def test_filters_by_property_id(self):
        assert "p.id = $1" in PROPERTY_DETAIL_SQL

    def test_projects_core_columns(self):
        for col in ("address_raw", "address_norm", "city", "county", "zip_code"):
            assert col in PROPERTY_DETAIL_SQL

    def test_projects_score_columns(self):
        for col in ("distress_score", "equity_pct", "equity_amount", "avm", "market_score"):
            assert col in PROPERTY_DETAIL_SQL

    def test_only_one_param_placeholder(self):
        assert "$1" in PROPERTY_DETAIL_SQL
        assert "$2" not in PROPERTY_DETAIL_SQL


# ── EVENTS_SQL ────────────────────────────────────────────────────────────────

class TestEventsSQL:
    def test_selects_from_events(self):
        assert "FROM events" in EVENTS_SQL

    def test_filters_by_property_id(self):
        assert "property_id = $1" in EVENTS_SQL

    def test_projects_event_type(self):
        assert "event_type" in EVENTS_SQL

    def test_projects_auction_date(self):
        assert "auction_date" in EVENTS_SQL

    def test_orders_by_filing_date_desc(self):
        assert "filing_date DESC" in EVENTS_SQL

    def test_only_one_param_placeholder(self):
        assert "$1" in EVENTS_SQL
        assert "$2" not in EVENTS_SQL


# ── ANALYSIS_SQL ──────────────────────────────────────────────────────────────

class TestAnalysisSQL:
    def test_selects_from_analysis(self):
        assert "FROM analysis a" in ANALYSIS_SQL

    def test_joins_valuations(self):
        assert "valuations v" in ANALYSIS_SQL

    def test_filters_by_property_id(self):
        assert "a.property_id = $1" in ANALYSIS_SQL

    def test_projects_mao(self):
        assert "a.mao" in ANALYSIS_SQL

    def test_projects_rehab_cost(self):
        assert "rehab_cost" in ANALYSIS_SQL

    def test_projects_record_type(self):
        assert "record_type" in ANALYSIS_SQL

    def test_projects_valuation_arv(self):
        assert "valuation_arv" in ANALYSIS_SQL or "v.arv" in ANALYSIS_SQL

    def test_orders_by_calculated_at_desc(self):
        assert "calculated_at DESC" in ANALYSIS_SQL

    def test_only_one_param_placeholder(self):
        assert "$1" in ANALYSIS_SQL
        assert "$2" not in ANALYSIS_SQL


# ── VALUATIONS_SQL ────────────────────────────────────────────────────────────

class TestValuationsSQL:
    def test_selects_from_valuations(self):
        assert "FROM valuations v" in VALUATIONS_SQL

    def test_filters_by_property_id(self):
        assert "v.property_id = $1" in VALUATIONS_SQL

    def test_projects_arv(self):
        assert "v.arv" in VALUATIONS_SQL

    def test_projects_avm(self):
        assert "v.avm" in VALUATIONS_SQL

    def test_projects_confidence_score(self):
        assert "confidence_score" in VALUATIONS_SQL

    def test_projects_arv_version(self):
        assert "arv_version" in VALUATIONS_SQL

    def test_orders_by_calculated_at_desc(self):
        assert "calculated_at DESC" in VALUATIONS_SQL

    def test_only_one_param_placeholder(self):
        assert "$1" in VALUATIONS_SQL
        assert "$2" not in VALUATIONS_SQL


# ── PROPERTY_EXISTS_SQL ───────────────────────────────────────────────────────

class TestPropertyExistsSQL:
    def test_selects_from_properties(self):
        assert "properties" in PROPERTY_EXISTS_SQL

    def test_filters_by_id(self):
        assert "id = $1" in PROPERTY_EXISTS_SQL

    def test_only_one_param_placeholder(self):
        assert "$1" in PROPERTY_EXISTS_SQL
        assert "$2" not in PROPERTY_EXISTS_SQL


# ── EQUITY_SQL ────────────────────────────────────────────────────────────────

class TestEquitySQL:
    def test_selects_from_latest_scores(self):
        assert "latest_property_scores" in EQUITY_SQL

    def test_filters_by_property_id(self):
        assert "property_id = $1" in EQUITY_SQL

    def test_projects_equity_fields(self):
        for col in ("equity_pct", "equity_amount", "estimated_liens", "tax_owed"):
            assert col in EQUITY_SQL

    def test_only_one_param_placeholder(self):
        assert "$1" in EQUITY_SQL
        assert "$2" not in EQUITY_SQL
