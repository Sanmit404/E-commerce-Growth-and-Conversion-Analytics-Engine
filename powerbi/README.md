# Power BI report

The report is built on the CSV extracts in `data/marts/`, which are written by
`ga4_growth.metrics.export_marts()`. Power BI never touches the DuckDB file
directly, so the numbers in the report are the same ones the notebooks use.

## Loading the data

Run the pipeline first so the CSVs exist:

```
python run_pipeline.py --marts
```

Then in Power BI Desktop:

1. Get data, Text/CSV, and pick every file in `data/marts/`.
2. In Power Query, set `event_date`, `order_date`, `acquisition_week` and
   `session_date` to Date, and every rate column to Decimal Number.
3. Load. Do not enable auto date/time, the date table below replaces it.
4. Paste the measures from `measures.dax` into a new table called `_Measures`.

If you would rather connect live, install the DuckDB ODBC driver and point Power
BI at `data/warehouse/ga4_growth.duckdb`. The CSV route is the one that has been
tested here because it needs no driver install.

## Tables

| Table | Grain | Used for |
| --- | --- | --- |
| fct_daily_kpis | one row per day | trend lines, week on week growth |
| fct_funnel_daily_segments | day by device by channel by country by user type | the funnel page and every slicer |
| funnel_by_* | one row per segment value | quick step rate bars |
| fct_orders | one row per order | order value distribution, repeat orders |
| fct_product_performance | one row per product | product and category pages |
| fct_cohort_retention | cohort week by channel by week index | retention matrix |
| acquisition_quality | one row per source and medium | acquisition scatter |

## Model

`dim_date` is a calculated table, everything else is imported.

```
dim_date = CALENDAR(DATE(2024,9,1), DATE(2024,11,30))
```

Relationships, all one to many and single direction from the dimension side:

- dim_date[Date] to fct_daily_kpis[event_date]
- dim_date[Date] to fct_funnel_daily_segments[session_date]
- dim_date[Date] to fct_orders[order_date]
- dim_product[product_id] to fct_product_performance[product_id], where
  dim_product comes from `data/raw/dim_products.csv`

`fct_cohort_retention` and `acquisition_quality` stay disconnected. They are
already aggregated on their own grain and joining them to the date table would
double count users.

`funnel_by_*` tables are also disconnected. They are there so a page can show a
segment breakdown without scanning the daily fact.

## Pages

1. Executive summary. Cards for sessions, orders, revenue, AOV, session
   conversion and repeat purchase rate. Line chart of sessions and revenue with
   the 7 day average. Week on week growth in a small multiple.
2. Funnel. A funnel visual driven by the step measures, with slicers for device,
   channel, country and new versus returning. A second visual shows step
   conversion so the slicers make the weak step obvious.
3. Acquisition. Scatter of user share against revenue per user from
   `acquisition_quality`, plus a table of the same columns.
4. Retention. Matrix of `acquisition_week` by `week_index` with the retention
   measure, conditional formatting on a blue scale.
5. Products. Table of products sorted by revenue, plus a scatter of sessions
   viewed against view to cart rate to find pages that get traffic and do not
   convert.

## Things worth knowing

The funnel steps are cumulative, so Add to cart already includes everyone who
later purchased. A Power BI funnel visual assumes this, which is why the marts
store cumulative counts rather than counts of people who stopped at each step.

Revenue in `fct_daily_kpis` is order level revenue. `fct_product_performance`
sums item level revenue, and the two differ slightly because shipping and
rounding sit at the order level. Do not put both on the same card.
