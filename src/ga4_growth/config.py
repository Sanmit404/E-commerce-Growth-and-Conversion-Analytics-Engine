"""Paths and shared settings for the analytics engine."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
WAREHOUSE_PATH = DATA_DIR / "warehouse" / "ga4_growth.duckdb"
MARTS_DIR = DATA_DIR / "marts"

SQL_DIR = ROOT / "sql"
DUCKDB_SQL_DIR = SQL_DIR / "duckdb"
BIGQUERY_SQL_DIR = SQL_DIR / "bigquery"

REPORTS_DIR = ROOT / "reports"
FIGURES_DIR = REPORTS_DIR / "figures"
TABLES_DIR = REPORTS_DIR / "tables"

# Window we simulate / query. Covers a full quarter so cohort retention and the
# Black Friday spike are both visible.
START_DATE = "2024-09-01"
END_DATE = "2024-11-30"

# Public GA4 export used by the BigQuery version of the same models.
BQ_SOURCE_TABLE = "bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*"

RANDOM_SEED = 42


def ensure_dirs() -> None:
    for path in [RAW_DIR, WAREHOUSE_PATH.parent, MARTS_DIR, FIGURES_DIR, TABLES_DIR]:
        path.mkdir(parents=True, exist_ok=True)
