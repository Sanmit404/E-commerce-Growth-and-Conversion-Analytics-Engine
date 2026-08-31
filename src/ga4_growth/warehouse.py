"""
Builds the analytics layer in DuckDB and hands query results back as pandas.

The models in sql/duckdb are ports of sql/bigquery. Running them locally keeps
the whole project reproducible on a laptop; the BigQuery versions are what would
run against the real GA4 export.
"""

from __future__ import annotations

import duckdb
import pandas as pd

from . import config

MODELS = [
    "01_stg_events.sql",
    "02_fct_sessions.sql",
    "03_fct_funnel.sql",
    "04_fct_orders.sql",
    "05_fct_product_performance.sql",
    "06_dim_users.sql",
    "07_fct_daily_kpis.sql",
    "08_fct_cohort_retention.sql",
]


def connect(read_only: bool = False) -> duckdb.DuckDBPyConnection:
    config.ensure_dirs()
    con = duckdb.connect(str(config.WAREHOUSE_PATH), read_only=read_only)
    if not read_only:
        register_raw_events(con)
    return con


def register_raw_events(con: duckdb.DuckDBPyConnection) -> None:
    """Point raw_events at the daily parquet shards, same idea as events_* in BigQuery."""
    glob = (config.RAW_DIR / "events_*.parquet").as_posix()
    con.execute(
        f"CREATE OR REPLACE VIEW raw_events AS SELECT * FROM read_parquet('{glob}', union_by_name = true)"
    )


def build(verbose: bool = True) -> None:
    con = connect()
    try:
        for model in MODELS:
            sql = (config.DUCKDB_SQL_DIR / model).read_text(encoding="utf-8")
            con.execute(sql)
            if verbose:
                table = model.split("_", 1)[1].replace(".sql", "")
                rows = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                print(f"built {table:<24} {rows:>10,} rows")
    finally:
        con.close()


def query(sql: str, params: list | None = None) -> pd.DataFrame:
    con = duckdb.connect(str(config.WAREHOUSE_PATH), read_only=True)
    try:
        return con.execute(sql, params or []).df()
    finally:
        con.close()


def table(name: str) -> pd.DataFrame:
    return query(f"SELECT * FROM {name}")


if __name__ == "__main__":
    build()
