"""
Streamlit dashboard over the DuckDB analytics layer.

Run it from the project root:

    streamlit run dashboard/app.py

Every number shown here comes from ga4_growth.metrics, so the dashboard cannot
drift away from the notebooks.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

import altair as alt
import pandas as pd
import streamlit as st

from ga4_growth import metrics, stats
from ga4_growth.warehouse import query

st.set_page_config(page_title="GA4 Growth and Conversion", page_icon=None, layout="wide")

DIMENSION_LABELS = {
    "Device": "device_category",
    "Channel": "channel_group",
    "Country": "country",
    "New or returning": "user_type",
    "Price band": "price_band",
    "Time of day": "day_part",
}


@st.cache_data(show_spinner=False)
def load_headline() -> pd.Series:
    return metrics.headline_kpis()


@st.cache_data(show_spinner=False)
def load_daily() -> pd.DataFrame:
    return metrics.daily_kpis()


@st.cache_data(show_spinner=False)
def load_funnel(where: str) -> pd.DataFrame:
    return metrics.funnel_overall(where)


@st.cache_data(show_spinner=False)
def load_funnel_by(dimension: str) -> pd.DataFrame:
    return metrics.funnel_by(dimension, min_sessions=0)


@st.cache_data(show_spinner=False)
def load_acquisition() -> pd.DataFrame:
    return metrics.acquisition_quality("source_medium")


@st.cache_data(show_spinner=False)
def load_cohorts() -> pd.DataFrame:
    return metrics.cohort_matrix("retention_rate")


@st.cache_data(show_spinner=False)
def filter_values(column: str) -> list[str]:
    return sorted(query(f"SELECT DISTINCT {column} AS v FROM fct_funnel WHERE {column} IS NOT NULL")["v"])


def build_where(picked: dict[str, list[str]]) -> str:
    parts = []
    for column, values in picked.items():
        if values:
            quoted = ", ".join("'" + v.replace("'", "''") + "'" for v in values)
            parts.append(f"{column} IN ({quoted})")
    return " AND ".join(parts) if parts else "TRUE"


st.title("Ecommerce growth and conversion")
st.caption(
    "GA4 style event data modelled into a session funnel. Numbers are for "
    "1 September to 30 November 2024."
)

page = st.sidebar.radio(
    "Page", ["Overview", "Funnel explorer", "Acquisition", "Retention", "Experiment sizing"]
)

if page == "Overview":
    kpi = load_headline()
    daily = load_daily()

    row1 = st.columns(5)
    row1[0].metric("Sessions", f"{kpi['sessions']:,.0f}")
    row1[1].metric("Users", f"{kpi['users']:,.0f}")
    row1[2].metric("Orders", f"{kpi['transactions']:,.0f}")
    row1[3].metric("Revenue", f"${kpi['revenue']:,.0f}")
    row1[4].metric("Average order value", f"${kpi['average_order_value']:,.2f}")

    row2 = st.columns(5)
    row2[0].metric("Session conversion", f"{kpi['session_conversion_rate']:.2%}")
    row2[1].metric("View to cart", f"{kpi['view_to_cart_rate']:.2%}")
    row2[2].metric("Cart abandonment", f"{kpi['cart_abandonment_rate']:.2%}")
    row2[3].metric("Checkout abandonment", f"{kpi['checkout_abandonment_rate']:.2%}")
    row2[4].metric("Repeat purchase rate", f"{kpi['repeat_purchase_rate']:.2%}")

    st.subheader("Daily trend")
    measure = st.selectbox(
        "Measure", ["sessions", "revenue", "transactions", "session_conversion_rate", "average_order_value"]
    )
    st.line_chart(daily.set_index("event_date")[measure], height=280)

    st.subheader("Full funnel")
    funnel = load_funnel("TRUE")
    chart_data = funnel[["step", "sessions", "cumulative_conversion"]].fillna(1.0)
    st.altair_chart(
        alt.Chart(chart_data)
        .mark_bar()
        .encode(
            y=alt.Y("step:N", sort=list(funnel["step"]), title=None),
            x=alt.X("sessions:Q", title="Sessions"),
            tooltip=["step", "sessions", alt.Tooltip("cumulative_conversion:Q", format=".2%")],
        )
        .properties(height=280),
        width="stretch",
    )

elif page == "Funnel explorer":
    st.subheader("Funnel with filters")
    picked = {}
    cols = st.columns(3)
    for i, column in enumerate(["device_category", "channel_group", "country"]):
        picked[column] = cols[i].multiselect(column.replace("_", " "), filter_values(column))

    where = build_where(picked)
    funnel = load_funnel(where)

    if funnel["sessions"].iloc[0] == 0:
        st.warning("No sessions match this filter.")
    else:
        show = funnel[["step", "sessions", "step_conversion", "cumulative_conversion", "dropped"]]
        st.dataframe(
            show.style.format({
                "sessions": "{:,.0f}", "dropped": "{:,.0f}",
                "step_conversion": "{:.2%}", "cumulative_conversion": "{:.2%}",
            }),
            width="stretch", hide_index=True,
        )

        st.subheader("Compare a dimension")
        label = st.selectbox("Split by", list(DIMENSION_LABELS))
        by = load_funnel_by(DIMENSION_LABELS[label])
        step = st.selectbox(
            "Step rate",
            ["product_view_rate", "view_to_cart_rate", "cart_to_checkout_rate",
             "shipping_to_payment_rate", "checkout_to_purchase_rate", "session_conversion_rate"],
            index=5,
        )
        st.altair_chart(
            alt.Chart(by)
            .mark_bar()
            .encode(
                x=alt.X(f"{step}:Q", title=step.replace("_", " "), axis=alt.Axis(format=".1%")),
                y=alt.Y("segment:N", sort="-x", title=None),
                tooltip=["segment", "sessions", alt.Tooltip(f"{step}:Q", format=".2%")],
            )
            .properties(height=max(220, 28 * len(by))),
            width="stretch",
        )

        numerator = {
            "product_view_rate": ("viewed_product", "sessions"),
            "view_to_cart_rate": ("added_to_cart", "viewed_product"),
            "cart_to_checkout_rate": ("began_checkout", "added_to_cart"),
            "shipping_to_payment_rate": ("added_payment", "added_shipping"),
            "checkout_to_purchase_rate": ("purchased", "began_checkout"),
            "session_conversion_rate": ("purchased", "sessions"),
        }[step]
        st.caption(
            "Each segment tested against the largest one with a two proportion z test, "
            "Holm adjusted."
        )
        st.dataframe(
            stats.compare_segments(by, "segment", numerator[0], numerator[1]).round(4),
            width="stretch", hide_index=True,
        )

elif page == "Acquisition":
    acq = load_acquisition()
    st.subheader("Volume against quality, first touch attributed")
    st.altair_chart(
        alt.Chart(acq)
        .mark_circle(size=180)
        .encode(
            x=alt.X("user_share:Q", title="Share of acquired users", axis=alt.Axis(format=".0%")),
            y=alt.Y("revenue_per_user:Q", title="Revenue per acquired user"),
            tooltip=["segment", "acquired_users", alt.Tooltip("revenue_per_user:Q", format="$.2f"),
                     alt.Tooltip("user_conversion_rate:Q", format=".2%")],
        )
        .properties(height=340),
        width="stretch",
    )
    st.dataframe(
        acq[["segment", "acquired_users", "user_share", "sessions_per_user", "view_to_cart_rate",
             "user_conversion_rate", "revenue_per_user", "revenue_share"]].round(4),
        width="stretch", hide_index=True,
    )

elif page == "Retention":
    st.subheader("Weekly retention by acquisition cohort")
    cohorts = load_cohorts().iloc[:, :9]
    long = cohorts.reset_index().melt("acquisition_week", var_name="week_index", value_name="retention")
    long = long.dropna()
    # Altair reads the cohort as a timestamp and prints epoch milliseconds, so
    # it is turned into a plain date string first.
    long["acquisition_week"] = pd.to_datetime(long["acquisition_week"]).dt.strftime("%Y-%m-%d")
    st.altair_chart(
        alt.Chart(long)
        .mark_rect()
        .encode(
            x=alt.X("week_index:O", title="Weeks since first visit"),
            y=alt.Y("acquisition_week:O", title="Cohort"),
            color=alt.Color("retention:Q", scale=alt.Scale(scheme="blues"), legend=None),
            tooltip=["acquisition_week", "week_index", alt.Tooltip("retention:Q", format=".1%")],
        )
        .properties(height=380),
        width="stretch",
    )

    st.subheader("Repeat purchase by acquisition channel")
    repeat = metrics.repeat_purchase_metrics()
    repeat["repeat_rate"] = repeat["repeat_customers"] / repeat["customers"]
    st.dataframe(repeat.round(3), width="stretch", hide_index=True)

else:
    st.subheader("How long would a test take")
    st.caption(
        "Sample size for a two sided test at 80% power and 5% significance, then "
        "turned into days using the traffic that actually reaches that step."
    )

    kpi = load_headline()
    device = load_funnel_by("device_category").set_index("segment")
    presets = {
        "Mobile shipping to payment": (
            float(device.loc["mobile", "shipping_to_payment_rate"]),
            float(device.loc["mobile", "added_shipping"]) / 91,
        ),
        "Cart to checkout": (float(kpi["cart_to_checkout_rate"]), 231.0),
        "View to cart": (float(kpi["view_to_cart_rate"]), 1585.0),
        "Session conversion, all traffic": (float(kpi["session_conversion_rate"]), 2508.0),
    }

    choice = st.selectbox("Metric to move", list(presets))
    baseline, daily_units = presets[choice]
    baseline = st.number_input("Baseline rate", value=round(baseline, 4), format="%.4f")
    daily_units = st.number_input("Units per day entering the test", value=float(round(daily_units)))
    mde = st.slider("Relative lift to detect", 0.01, 0.30, 0.05, 0.01)

    if baseline * (1 + mde) >= 1:
        st.warning("That lift would take the rate past 100%. Pick a smaller one.")
        st.stop()

    plan = stats.experiment_plan(choice, baseline, daily_units / 2, mde)
    left, right = st.columns(2)
    left.metric("Sample per arm", f"{plan['n_per_arm']:,}")
    right.metric("Days needed", f"{plan['days_needed']:,}")

    # Lifts that would push the rate past 100% are skipped, which matters for a
    # step like shipping to payment where the baseline is already near 80%.
    curve = pd.DataFrame([
        {"relative_mde": m, "days": stats.experiment_plan(choice, baseline, daily_units / 2, m)["days_needed"]}
        for m in [0.02, 0.03, 0.05, 0.08, 0.10, 0.15, 0.20, 0.30]
        if baseline * (1 + m) < 1
    ])
    st.altair_chart(
        alt.Chart(curve)
        .mark_line(point=True)
        .encode(
            x=alt.X("relative_mde:Q", title="Relative lift", axis=alt.Axis(format=".0%")),
            y=alt.Y("days:Q", title="Days needed", scale=alt.Scale(type="log")),
        )
        .properties(height=300),
        width="stretch",
    )
