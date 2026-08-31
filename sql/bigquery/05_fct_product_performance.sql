-- fct_product_performance
-- Grain: one row per product.
-- Joins the discovery side (views, cart adds) to the money side (units, revenue)
-- so a product can be judged on conversion and not only on revenue.

CREATE OR REPLACE TABLE ga4_growth.fct_product_performance AS
WITH item_events AS (
  SELECT
    product_id,
    ANY_VALUE(product_name)      AS product_name,
    ANY_VALUE(product_category)  AS product_category,
    AVG(price)                   AS avg_price,
    COUNT(DISTINCT IF(event_name = 'view_item',        session_id, NULL)) AS sessions_viewed,
    COUNT(DISTINCT IF(event_name = 'add_to_cart',      session_id, NULL)) AS sessions_added,
    COUNT(DISTINCT IF(event_name = 'remove_from_cart', session_id, NULL)) AS sessions_removed,
    COUNT(DISTINCT IF(event_name = 'begin_checkout',   session_id, NULL)) AS sessions_checkout,
    COUNT(DISTINCT IF(event_name = 'purchase',         transaction_id, NULL)) AS orders,
    SUM(IF(event_name = 'purchase', quantity, 0))                         AS units_sold,
    ROUND(SUM(IF(event_name = 'purchase', item_revenue, 0)), 2)           AS revenue
  FROM ga4_growth.stg_events
  WHERE product_id IS NOT NULL
  GROUP BY product_id
)

SELECT
  product_id,
  product_name,
  product_category,
  ROUND(avg_price, 2)                                                AS avg_price,
  sessions_viewed,
  sessions_added,
  sessions_removed,
  sessions_checkout,
  orders,
  units_sold,
  revenue,
  ROUND(SAFE_DIVIDE(sessions_added, NULLIF(sessions_viewed, 0)), 4)  AS view_to_cart_rate,
  ROUND(SAFE_DIVIDE(orders, NULLIF(sessions_added, 0)), 4)           AS cart_to_order_rate,
  ROUND(SAFE_DIVIDE(orders, NULLIF(sessions_viewed, 0)), 4)          AS view_to_order_rate,
  ROUND(SAFE_DIVIDE(sessions_removed, NULLIF(sessions_added, 0)), 4) AS cart_removal_rate,
  DENSE_RANK() OVER (ORDER BY revenue DESC)                          AS revenue_rank,
  DENSE_RANK() OVER (PARTITION BY product_category ORDER BY revenue DESC) AS revenue_rank_in_category,
  ROUND(SAFE_DIVIDE(revenue, SUM(revenue) OVER ()), 4)               AS revenue_share,
  ROUND(SUM(revenue) OVER (ORDER BY revenue DESC ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
        / NULLIF(SUM(revenue) OVER (), 0), 4)                        AS cumulative_revenue_share
FROM item_events;
