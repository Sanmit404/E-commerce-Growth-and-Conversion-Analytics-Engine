-- fct_orders
-- Grain: one row per transaction.
-- order_value uses ecommerce.purchase_revenue, which is what the store reports.
-- item_revenue_sum re-adds price * quantity from the items array so the two can
-- be reconciled in the data quality checks.

CREATE OR REPLACE TABLE ga4_growth.fct_orders AS
WITH purchase_items AS (
  SELECT
    transaction_id,
    session_id,
    user_id,
    event_timestamp,
    event_date,
    device_category,
    country,
    source,
    medium,
    campaign,
    channel_group,
    product_id,
    product_name,
    product_category,
    price,
    quantity,
    item_revenue,
    purchase_revenue
  FROM ga4_growth.stg_events
  WHERE event_name = 'purchase'
    AND transaction_id IS NOT NULL
),

orders AS (
  SELECT
    transaction_id,
    ANY_VALUE(session_id)               AS session_id,
    ANY_VALUE(user_id)                  AS user_id,
    MIN(event_timestamp)                AS order_timestamp,
    MIN(event_date)                     AS order_date,
    ANY_VALUE(device_category)          AS device_category,
    ANY_VALUE(country)                  AS country,
    ANY_VALUE(source)                   AS source,
    ANY_VALUE(medium)                   AS medium,
    ANY_VALUE(campaign)                 AS campaign,
    ANY_VALUE(channel_group)            AS channel_group,
    MAX(purchase_revenue)               AS order_value,
    ROUND(SUM(item_revenue), 2)         AS item_revenue_sum,
    SUM(quantity)                       AS item_count,
    COUNT(DISTINCT product_id)          AS distinct_products,
    COUNT(DISTINCT product_category)    AS distinct_categories,
    ARRAY_AGG(DISTINCT product_category IGNORE NULLS ORDER BY product_category) AS categories
  FROM purchase_items
  GROUP BY transaction_id
)

SELECT
  o.*,
  -- Order sequence per customer drives repeat purchase and time-to-second-order.
  ROW_NUMBER() OVER (PARTITION BY o.user_id ORDER BY o.order_timestamp)     AS order_seq,
  ROW_NUMBER() OVER (PARTITION BY o.user_id ORDER BY o.order_timestamp) = 1 AS is_first_order,
  DATE_DIFF(
    o.order_date,
    LAG(o.order_date) OVER (PARTITION BY o.user_id ORDER BY o.order_timestamp),
    DAY
  )                                                                         AS days_since_previous_order,
  SAFE_DIVIDE(o.order_value, NULLIF(o.item_count, 0))                       AS avg_item_value,
  EXTRACT(HOUR FROM o.order_timestamp)                                      AS order_hour,
  FORMAT_DATE('%A', o.order_date)                                           AS order_day_of_week,
  DENSE_RANK() OVER (ORDER BY o.order_value DESC)                           AS order_value_rank
FROM orders AS o;
