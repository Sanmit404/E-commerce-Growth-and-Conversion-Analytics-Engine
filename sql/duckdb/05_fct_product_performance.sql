-- fct_product_performance (DuckDB port of sql/bigquery/05_fct_product_performance.sql)
-- Grain: one row per product.

CREATE OR REPLACE TABLE fct_product_performance AS
WITH item_events AS (
  SELECT
    product_id,
    any_value(product_name)     AS product_name,
    any_value(product_category) AS product_category,
    avg(price)                  AS avg_price,
    count(DISTINCT session_id)     FILTER (WHERE event_name = 'view_item')        AS sessions_viewed,
    count(DISTINCT session_id)     FILTER (WHERE event_name = 'add_to_cart')      AS sessions_added,
    count(DISTINCT session_id)     FILTER (WHERE event_name = 'remove_from_cart') AS sessions_removed,
    count(DISTINCT session_id)     FILTER (WHERE event_name = 'begin_checkout')   AS sessions_checkout,
    count(DISTINCT transaction_id) FILTER (WHERE event_name = 'purchase')         AS orders,
    coalesce(sum(quantity)     FILTER (WHERE event_name = 'purchase'), 0)         AS units_sold,
    round(coalesce(sum(item_revenue) FILTER (WHERE event_name = 'purchase'), 0), 2) AS revenue
  FROM stg_events
  WHERE product_id IS NOT NULL
  GROUP BY product_id
)

SELECT
  product_id,
  product_name,
  product_category,
  round(avg_price, 2)                                        AS avg_price,
  sessions_viewed,
  sessions_added,
  sessions_removed,
  sessions_checkout,
  orders,
  units_sold,
  revenue,
  round(sessions_added / nullif(sessions_viewed, 0), 4)      AS view_to_cart_rate,
  round(orders / nullif(sessions_added, 0), 4)               AS cart_to_order_rate,
  round(orders / nullif(sessions_viewed, 0), 4)              AS view_to_order_rate,
  round(sessions_removed / nullif(sessions_added, 0), 4)     AS cart_removal_rate,
  dense_rank() OVER (ORDER BY revenue DESC)                  AS revenue_rank,
  dense_rank() OVER (PARTITION BY product_category ORDER BY revenue DESC) AS revenue_rank_in_category,
  round(revenue / nullif(sum(revenue) OVER (), 0), 4)        AS revenue_share,
  round(sum(revenue) OVER (ORDER BY revenue DESC ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
        / nullif(sum(revenue) OVER (), 0), 4)                AS cumulative_revenue_share
FROM item_events;
