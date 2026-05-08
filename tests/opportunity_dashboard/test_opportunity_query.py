"""
Unit tests for services.opportunity_dashboard.query.build_query.

Covers:
  - No filters: WHERE clause omitted; LIMIT/OFFSET params present
  - county filter adds WHERE p.county = $1
  - case_type filter adds WHERE e_latest.event_type::TEXT = $1
  - min_distress_score adds WHERE s.distress_score >= $1
  - min_equity_pct adds WHERE s.equity_pct >= $1
  - auction_date_before adds WHERE e_latest.auction_date <= $1
  - Multiple filters: parameters numbered sequentially ($1, $2, …)
  - sort_by=equity_pct uses s.equity_pct in ORDER BY
  - sort_dir=asc uses ASC NULLS FIRST
  - sort_dir=desc uses DESC NULLS LAST (default)
  - count query shares the same filters but omits ORDER BY / LIMIT / OFFSET
  - count query contains no LIMIT or OFFSET
  - page/page_size translate correctly to LIMIT and OFFSET values
"""

from datetime import date

import pytest

from services.opportunity_dashboard.query import build_query


def _q(**kw):
    defaults = dict(
        county=None, case_type=None, min_distress_score=None,
        min_equity_pct=None, auction_date_before=None,
        sort_by="distress_score", sort_dir="desc",
        limit=20, offset=0,
    )
    defaults.update(kw)
    return build_query(**defaults)


# ── no filters ────────────────────────────────────────────────────────────────

class TestNoFilters:
    def test_no_where_clause(self):
        sql, params, *_ = _q()
        # LATERAL subqueries contain indented "    WHERE property_id = …";
        # the outer filter WHERE is unindented: "\nWHERE ".
        assert "\nWHERE " not in sql

    def test_limit_offset_in_params(self):
        _, params, *_ = _q(limit=20, offset=0)
        assert 20 in params
        assert 0 in params

    def test_limit_offset_are_last_two_params(self):
        _, params, *_ = _q(limit=15, offset=40)
        assert params[-2] == 15
        assert params[-1] == 40


# ── single filters ────────────────────────────────────────────────────────────

class TestSingleFilters:
    def test_county_where_clause(self):
        sql, params, *_ = _q(county="Travis")
        assert "p.county = $1" in sql
        assert params[0] == "Travis"

    def test_case_type_where_clause(self):
        sql, params, *_ = _q(case_type="foreclosure")
        assert "e_latest.event_type::TEXT = $1" in sql
        assert params[0] == "foreclosure"

    def test_min_distress_score_where_clause(self):
        sql, params, *_ = _q(min_distress_score=60.0)
        assert "s.distress_score >= $1" in sql
        assert params[0] == 60.0

    def test_min_equity_pct_where_clause(self):
        sql, params, *_ = _q(min_equity_pct=25.0)
        assert "s.equity_pct >= $1" in sql
        assert params[0] == 25.0

    def test_auction_date_before_where_clause(self):
        d = date(2025, 6, 1)
        sql, params, *_ = _q(auction_date_before=d)
        assert "e_latest.auction_date <= $1" in sql
        assert params[0] == d


# ── multiple filters — parameter numbering ────────────────────────────────────

class TestMultipleFilters:
    def test_two_filters_numbered_sequentially(self):
        sql, params, *_ = _q(county="Hays", min_distress_score=50.0)
        assert "$1" in sql
        assert "$2" in sql
        assert params[0] == "Hays"
        assert params[1] == 50.0

    def test_all_five_filters(self):
        d = date(2025, 9, 1)
        sql, params, *_ = _q(
            county="Travis",
            case_type="tax_delinquency",
            min_distress_score=40.0,
            min_equity_pct=10.0,
            auction_date_before=d,
        )
        # 5 filter params + limit + offset = 7 total
        assert len(params) == 7
        assert params[0] == "Travis"
        assert params[1] == "tax_delinquency"
        assert params[2] == 40.0
        assert params[3] == 10.0
        assert params[4] == d


# ── sort ──────────────────────────────────────────────────────────────────────

class TestSort:
    def test_default_sort_distress_score_desc(self):
        sql, *_ = _q()
        assert "s.distress_score DESC NULLS LAST" in sql

    def test_sort_by_equity_pct(self):
        sql, *_ = _q(sort_by="equity_pct")
        assert "s.equity_pct" in sql

    def test_sort_by_auction_date(self):
        sql, *_ = _q(sort_by="auction_date")
        assert "e_latest.auction_date" in sql

    def test_sort_by_mao(self):
        sql, *_ = _q(sort_by="mao")
        assert "a_latest.mao" in sql

    def test_sort_dir_asc_nulls_first(self):
        sql, *_ = _q(sort_dir="asc")
        assert "ASC NULLS FIRST" in sql


# ── count query ───────────────────────────────────────────────────────────────

class TestCountQuery:
    def test_count_query_has_no_limit(self):
        _, _, count_sql, _ = _q(county="Travis")
        # LATERAL subqueries use "LIMIT 1" (literal); outer LIMIT uses a param "LIMIT $N".
        assert "LIMIT $" not in count_sql

    def test_count_query_has_no_offset(self):
        _, _, count_sql, _ = _q(county="Travis")
        assert "OFFSET" not in count_sql

    def test_count_query_has_same_filter_params(self):
        _, _, count_sql, count_params = _q(county="Travis", min_distress_score=70.0)
        assert count_params == ["Travis", 70.0]

    def test_count_query_no_filter_has_empty_params(self):
        _, _, _, count_params = _q()
        assert count_params == []

    def test_count_query_contains_count_star(self):
        _, _, count_sql, _ = _q()
        assert "COUNT(*)" in count_sql


# ── pagination offset ─────────────────────────────────────────────────────────

class TestPagination:
    def test_offset_zero_for_page_1(self):
        _, params, *_ = _q(limit=20, offset=0)
        assert params[-1] == 0

    def test_offset_20_for_page_2(self):
        _, params, *_ = _q(limit=20, offset=20)
        assert params[-1] == 20

    def test_limit_in_params(self):
        _, params, *_ = _q(limit=50, offset=100)
        assert params[-2] == 50
        assert params[-1] == 100
