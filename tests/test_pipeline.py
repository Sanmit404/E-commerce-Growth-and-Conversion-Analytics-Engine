"""Checks that would catch a broken model before anyone reads a chart.

Run with:  pytest -q
The warehouse has to exist first:  python run_pipeline.py --all
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ga4_growth import config, metrics, stats  # noqa: E402
from ga4_growth.warehouse import MODELS, query  # noqa: E402

pytestmark = pytest.mark.skipif(
    not config.WAREHOUSE_PATH.exists(),
    reason="warehouse not built, run python run_pipeline.py --all",
)


@pytest.fixture(scope="module")
def funnel():
    return metrics.funnel_overall()


@pytest.fixture(scope="module")
def kpis():
    return metrics.headline_kpis()


def test_sql_models_match_between_engines():
    """Every DuckDB model has a BigQuery twin with the same name."""
    duck = {p.name for p in config.DUCKDB_SQL_DIR.glob("*.sql")}
    bq = {p.name for p in config.BIGQUERY_SQL_DIR.glob("*.sql")}
    assert duck == bq
    assert duck == set(MODELS)


def test_funnel_only_shrinks(funnel):
    counts = funnel["sessions"].tolist()
    for step, (a, b) in enumerate(zip(counts, counts[1:])):
        assert b <= a, f"step {step + 1} has more sessions than the step before it"


def test_cumulative_rate_matches_counts(funnel):
    total = funnel["sessions"].iloc[0]
    for _, row in funnel.iterrows():
        assert abs(row["cumulative_conversion"] - row["sessions"] / total) < 1e-9


def test_no_purchase_without_a_cart():
    bad = query(
        "SELECT count(*) AS n FROM fct_funnel WHERE purchased AND NOT added_to_cart"
    )["n"].iloc[0]
    assert bad == 0


def test_no_checkout_without_a_cart():
    bad = query(
        "SELECT count(*) AS n FROM fct_funnel WHERE began_checkout AND NOT added_to_cart"
    )["n"].iloc[0]
    assert bad == 0


def test_transaction_ids_are_unique():
    dupes = query(
        """
        SELECT count(*) AS n FROM (
          SELECT transaction_id FROM fct_orders
          GROUP BY transaction_id HAVING count(*) > 1
        )
        """
    )["n"].iloc[0]
    assert dupes == 0


def test_one_row_per_session_in_the_funnel():
    dupes = query(
        """
        SELECT count(*) AS n FROM (
          SELECT session_id FROM fct_funnel
          GROUP BY session_id HAVING count(*) > 1
        )
        """
    )["n"].iloc[0]
    assert dupes == 0


def test_orders_reconcile_with_the_funnel(kpis):
    orders = query("SELECT count(*) AS n FROM fct_orders")["n"].iloc[0]
    assert orders == kpis["transactions"]


def test_daily_kpis_cover_the_configured_window():
    row = query(
        "SELECT min(event_date) AS lo, max(event_date) AS hi, count(*) AS n FROM fct_daily_kpis"
    ).iloc[0]
    assert str(row["lo"])[:10] >= config.START_DATE
    assert str(row["hi"])[:10] <= config.END_DATE
    assert row["n"] > 80


def test_headline_rates_are_plausible(kpis):
    assert 0.001 < kpis["session_conversion_rate"] < 0.15
    assert 0.02 < kpis["view_to_cart_rate"] < 0.5
    assert 0.1 < kpis["cart_to_checkout_rate"] < 0.9
    assert 10 < kpis["average_order_value"] < 500
    assert kpis["sessions"] >= kpis["users"]


def test_revenue_is_never_negative():
    bad = query("SELECT count(*) AS n FROM fct_orders WHERE order_value < 0")["n"].iloc[0]
    assert bad == 0


def test_cohort_retention_starts_at_one():
    week0 = query(
        "SELECT DISTINCT retention_rate FROM fct_cohort_retention WHERE week_index = 0"
    )["retention_rate"].tolist()
    assert week0 == [1.0]


def test_funnel_by_dimension_rejects_unknown_columns():
    with pytest.raises(ValueError):
        metrics.funnel_by("device_category; DROP TABLE fct_funnel")


def test_segment_sessions_add_up_to_the_total(kpis):
    by_device = metrics.funnel_by("device_category", min_sessions=0)
    assert by_device["sessions"].sum() == kpis["sessions"]


def test_wilson_interval_brackets_the_rate():
    lo, hi = stats.wilson_ci(50, 200)
    assert lo < 0.25 < hi
    assert 0 <= lo and hi <= 1


def test_two_proportion_test_finds_an_obvious_gap():
    result = stats.two_proportion_test(100, 1000, 200, 1000)
    assert result.p_value < 0.001
    assert result.absolute_diff > 0


def test_impossible_lift_is_rejected_not_silently_nan():
    with pytest.raises(ValueError):
        stats.sample_size_per_arm(0.80, 0.30)
