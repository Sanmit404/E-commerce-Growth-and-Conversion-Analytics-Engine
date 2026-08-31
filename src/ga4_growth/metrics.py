"""
Reusable metric queries on top of the analytics layer.

Every rate is defined once here. The notebooks, the Streamlit app and the Power
BI extract all call these functions, so a metric cannot mean two different
things in two different places.
"""

from __future__ import annotations

import pandas as pd

from . import config
from .warehouse import query

STEP_COLUMNS = [
    ("session_started", "Session"),
    ("viewed_product", "Product view"),
    ("added_to_cart", "Add to cart"),
    ("viewed_cart", "View cart"),
    ("began_checkout", "Begin checkout"),
    ("added_shipping", "Shipping info"),
    ("added_payment", "Payment info"),
    ("purchased", "Purchase"),
]

ALLOWED_DIMENSIONS = {
    "device_category",
    "operating_system",
    "browser",
    "country",
    "channel_group",
    "source_medium",
    "source",
    "medium",
    "campaign",
    "user_type",
    "primary_category",
    "price_band",
    "day_of_week",
    "day_part",
    "session_hour",
    "is_weekend",
}


def _check_dimension(dimension: str) -> str:
    if dimension not in ALLOWED_DIMENSIONS:
        raise ValueError(f"{dimension} is not a slicing column on fct_funnel")
    return dimension


def headline_kpis() -> pd.Series:
    df = query(
        """
        WITH s AS (
          SELECT
            count(DISTINCT user_id)                 AS users,
            count(*)                                AS sessions,
            count(*) FILTER (WHERE session_seq = 1) AS new_user_sessions,
            count(*) FILTER (WHERE viewed_product)  AS product_view_sessions,
            count(*) FILTER (WHERE added_to_cart)   AS cart_sessions,
            count(*) FILTER (WHERE began_checkout)  AS checkout_sessions,
            count(*) FILTER (WHERE purchased)       AS purchase_sessions
          FROM fct_funnel
        ),
        o AS (
          SELECT
            count(*)                              AS transactions,
            sum(order_value)                      AS revenue,
            sum(item_count)                       AS items_sold,
            count(*) FILTER (WHERE order_seq > 1) AS repeat_orders,
            coalesce(sum(order_value) FILTER (WHERE order_seq > 1), 0) AS repeat_revenue
          FROM fct_orders
        ),
        u AS (
          SELECT
            count(*) FILTER (WHERE is_customer)        AS customers,
            count(*) FILTER (WHERE is_repeat_customer) AS repeat_customers,
            count(*) FILTER (WHERE is_returning_user)  AS returning_users
          FROM dim_users
        )
        SELECT
          s.users,
          s.sessions,
          u.returning_users,
          o.transactions,
          round(o.revenue, 2)                                     AS revenue,
          round(s.sessions / s.users, 3)                          AS sessions_per_user,
          round(s.product_view_sessions / s.sessions, 4)          AS product_view_rate,
          round(s.cart_sessions / s.product_view_sessions, 4)     AS view_to_cart_rate,
          round(s.checkout_sessions / s.cart_sessions, 4)         AS cart_to_checkout_rate,
          round(s.purchase_sessions / s.checkout_sessions, 4)     AS checkout_to_purchase_rate,
          round(s.purchase_sessions / s.sessions, 4)              AS session_conversion_rate,
          round(1 - s.checkout_sessions / s.cart_sessions, 4)     AS cart_abandonment_rate,
          round(1 - s.purchase_sessions / s.checkout_sessions, 4) AS checkout_abandonment_rate,
          round(o.revenue / o.transactions, 2)                    AS average_order_value,
          round(o.revenue / s.users, 2)                           AS revenue_per_user,
          round(o.revenue / s.sessions, 2)                        AS revenue_per_session,
          round(o.items_sold / o.transactions, 2)                 AS items_per_order,
          round(u.returning_users / s.users, 4)                   AS returning_user_rate,
          round(u.repeat_customers / u.customers, 4)              AS repeat_purchase_rate,
          round(o.repeat_revenue / o.revenue, 4)                  AS repeat_revenue_share
        FROM s, o, u
        """
    )
    return df.iloc[0]


def daily_kpis() -> pd.DataFrame:
    return query("SELECT * FROM fct_daily_kpis ORDER BY event_date")


def funnel_overall(where: str = "TRUE") -> pd.DataFrame:
    """Step counts, step conversion, cumulative conversion and drop-off."""
    parts = ", ".join(
        f"count(*) FILTER (WHERE {col}) AS \"{label}\"" for col, label in STEP_COLUMNS
    )
    wide = query(f"SELECT {parts} FROM fct_funnel WHERE {where}")
    long = wide.T.reset_index()
    long.columns = ["step", "sessions"]
    long["step_order"] = range(len(long))
    long["step_conversion"] = long["sessions"] / long["sessions"].shift(1)
    long["cumulative_conversion"] = long["sessions"] / long["sessions"].iloc[0]
    long["dropped"] = long["sessions"].shift(1) - long["sessions"]
    long["drop_off_rate"] = 1 - long["step_conversion"]
    return long


def funnel_by(dimension: str, min_sessions: int = 500) -> pd.DataFrame:
    """Funnel step rates for every value of one dimension."""
    dim = _check_dimension(dimension)
    parts = ", ".join(
        f"count(*) FILTER (WHERE {col}) AS {col}" for col, _ in STEP_COLUMNS[1:]
    )
    df = query(
        f"""
        SELECT
          {dim} AS segment,
          count(*)      AS sessions,
          count(DISTINCT user_id) AS users,
          {parts},
          round(sum(session_revenue), 2) AS revenue
        FROM fct_funnel
        GROUP BY 1
        HAVING count(*) >= {int(min_sessions)}
        ORDER BY sessions DESC
        """
    )
    df["product_view_rate"] = df["viewed_product"] / df["sessions"]
    df["view_to_cart_rate"] = df["added_to_cart"] / df["viewed_product"]
    df["cart_to_checkout_rate"] = df["began_checkout"] / df["added_to_cart"]
    df["shipping_to_payment_rate"] = df["added_payment"] / df["added_shipping"]
    df["checkout_to_purchase_rate"] = df["purchased"] / df["began_checkout"]
    df["session_conversion_rate"] = df["purchased"] / df["sessions"]
    df["cart_abandonment_rate"] = 1 - df["began_checkout"] / df["added_to_cart"]
    df["checkout_abandonment_rate"] = 1 - df["purchased"] / df["began_checkout"]
    df["revenue_per_session"] = df["revenue"] / df["sessions"]
    return df


def acquisition_quality(level: str = "source_medium") -> pd.DataFrame:
    """Volume against quality for each acquisition segment, first touch attributed."""
    dim = _check_dimension(level)
    segment_expr = (
        "acquisition_channel"
        if dim == "channel_group"
        else "acquisition_source || ' / ' || acquisition_medium"
    )
    users = query(
        f"""
        SELECT
          {segment_expr} AS segment,
          count(*)                                    AS acquired_users,
          count(*) FILTER (WHERE is_returning_user)   AS returning_users,
          count(*) FILTER (WHERE is_customer)         AS customers,
          count(*) FILTER (WHERE is_repeat_customer)  AS repeat_customers,
          round(sum(total_revenue), 2)                AS revenue,
          round(avg(total_sessions), 2)               AS sessions_per_user,
          round(avg(total_product_views), 2)          AS product_views_per_user,
          round(avg(days_to_first_purchase), 1)       AS avg_days_to_first_purchase
        FROM dim_users
        GROUP BY 1
        """
    )
    sessions = funnel_by(dim, min_sessions=0)[
        ["segment", "sessions", "added_to_cart", "began_checkout", "purchased",
         "view_to_cart_rate", "session_conversion_rate", "revenue_per_session"]
    ]
    out = users.merge(sessions, on="segment", how="left")
    out["user_conversion_rate"] = out["customers"] / out["acquired_users"]
    out["repeat_customer_rate"] = out["repeat_customers"] / out["customers"].replace(0, pd.NA)
    out["revenue_per_user"] = out["revenue"] / out["acquired_users"]
    out["returning_user_rate"] = out["returning_users"] / out["acquired_users"]
    out["user_share"] = out["acquired_users"] / out["acquired_users"].sum()
    out["revenue_share"] = out["revenue"] / out["revenue"].sum()
    return out.sort_values("acquired_users", ascending=False).reset_index(drop=True)


def cohort_matrix(metric: str = "retention_rate", channel: str | None = None) -> pd.DataFrame:
    if metric not in {"retention_rate", "purchase_rate", "revenue_per_cohort_user"}:
        raise ValueError("unsupported cohort metric")
    where = "TRUE" if channel is None else "acquisition_channel = ?"
    params = [] if channel is None else [channel]
    df = query(
        f"""
        SELECT
          acquisition_week,
          week_index,
          sum(cohort_users)     AS cohort_users,
          sum(active_users)     AS active_users,
          sum(purchasing_users) AS purchasing_users,
          sum(revenue)          AS revenue
        FROM fct_cohort_retention
        WHERE {where}
        GROUP BY acquisition_week, week_index
        ORDER BY acquisition_week, week_index
        """,
        params,
    )
    df["retention_rate"] = df["active_users"] / df["cohort_users"]
    df["purchase_rate"] = df["purchasing_users"] / df["cohort_users"]
    df["revenue_per_cohort_user"] = df["revenue"] / df["cohort_users"]
    return df.pivot(index="acquisition_week", columns="week_index", values=metric)


def repeat_purchase_metrics() -> pd.DataFrame:
    return query(
        """
        SELECT
          acquisition_channel,
          count(*) FILTER (WHERE is_customer)                    AS customers,
          count(*) FILTER (WHERE is_repeat_customer)             AS repeat_customers,
          round(avg(days_to_first_purchase), 1)                  AS days_to_first_purchase,
          round(avg(days_to_second_purchase), 1)                 AS days_to_second_purchase,
          round(avg(total_orders) FILTER (WHERE is_customer), 2) AS orders_per_customer,
          round(avg(average_order_value), 2)                     AS aov,
          round(sum(total_revenue), 2)                           AS revenue
        FROM dim_users
        GROUP BY 1
        ORDER BY revenue DESC
        """
    )


def product_performance(min_views: int = 200) -> pd.DataFrame:
    return query(
        f"""
        SELECT *
        FROM fct_product_performance
        WHERE sessions_viewed >= {int(min_views)}
        ORDER BY revenue DESC
        """
    )


def category_performance() -> pd.DataFrame:
    return query(
        """
        SELECT
          product_category,
          count(*)                                          AS products,
          sum(sessions_viewed)                              AS sessions_viewed,
          sum(sessions_added)                               AS sessions_added,
          sum(orders)                                       AS orders,
          sum(units_sold)                                   AS units_sold,
          round(sum(revenue), 2)                            AS revenue,
          round(sum(sessions_added) / sum(sessions_viewed), 4) AS view_to_cart_rate,
          round(sum(orders) / sum(sessions_viewed), 4)      AS view_to_order_rate,
          round(avg(avg_price), 2)                          AS avg_price,
          round(sum(revenue) / sum(sessions_viewed), 2)     AS revenue_per_view_session
        FROM fct_product_performance
        GROUP BY 1
        ORDER BY revenue DESC
        """
    )


def checkout_timing() -> pd.DataFrame:
    """How long each checkout step takes, split by device."""
    return query(
        """
        SELECT
          device_category,
          count(*) FILTER (WHERE began_checkout)                       AS checkouts,
          round(median(sec_cart_to_checkout)     FILTER (WHERE began_checkout), 1) AS median_cart_to_checkout,
          round(median(sec_shipping_to_payment)  FILTER (WHERE added_payment), 1)  AS median_shipping_to_payment,
          round(median(sec_checkout_to_purchase) FILTER (WHERE purchased), 1)      AS median_checkout_to_purchase
        FROM fct_funnel
        GROUP BY 1
        ORDER BY checkouts DESC
        """
    )


def session_model_frame() -> pd.DataFrame:
    """Session level frame used for the logistic regression on purchase."""
    return query(
        """
        SELECT
          purchased::INT      AS purchased,
          added_to_cart::INT  AS added_to_cart,
          device_category,
          channel_group,
          user_type,
          country,
          day_part,
          coalesce(primary_category, 'None') AS primary_category,
          products_viewed,
          pageviews,
          session_duration_sec,
          coalesce(avg_viewed_price, 0) AS avg_viewed_price
        FROM fct_funnel
        WHERE viewed_product
        """
    )


def funnel_step_labels() -> list[str]:
    return [label for _, label in STEP_COLUMNS]


def export_marts() -> list[str]:
    """Write the model tables to CSV for the Power BI file."""
    config.ensure_dirs()
    written = []
    for name in [
        "fct_daily_kpis",
        "fct_cohort_retention",
        "fct_product_performance",
        "fct_orders",
    ]:
        df = query(f"SELECT * FROM {name}")
        path = config.MARTS_DIR / f"{name}.csv"
        df.to_csv(path, index=False)
        written.append(path.name)

    # fct_funnel is 200k+ rows, so Power BI gets a pre-aggregated version.
    for dim in ["device_category", "channel_group", "country", "user_type", "price_band", "day_part"]:
        df = funnel_by(dim, min_sessions=0)
        df.insert(0, "dimension", dim)
        path = config.MARTS_DIR / f"funnel_by_{dim}.csv"
        df.to_csv(path, index=False)
        written.append(path.name)

    seg = query(
        """
        SELECT
          f.session_date,
          f.device_category,
          f.channel_group,
          f.country,
          f.user_type,
          count(*)                                AS sessions,
          count(*) FILTER (WHERE viewed_product)  AS viewed_product,
          count(*) FILTER (WHERE added_to_cart)   AS added_to_cart,
          count(*) FILTER (WHERE began_checkout)  AS began_checkout,
          count(*) FILTER (WHERE added_shipping)  AS added_shipping,
          count(*) FILTER (WHERE added_payment)   AS added_payment,
          count(*) FILTER (WHERE purchased)       AS purchased,
          round(sum(session_revenue), 2)          AS revenue
        FROM fct_funnel AS f
        GROUP BY ALL
        """
    )
    seg.to_csv(config.MARTS_DIR / "fct_funnel_daily_segments.csv", index=False)
    written.append("fct_funnel_daily_segments.csv")

    acquisition_quality("source_medium").to_csv(config.MARTS_DIR / "acquisition_quality.csv", index=False)
    written.append("acquisition_quality.csv")
    return written


if __name__ == "__main__":
    print(headline_kpis().to_string())
    print()
    print(funnel_overall().to_string(index=False))
