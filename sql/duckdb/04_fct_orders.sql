-- fct_orders (DuckDB port of sql/bigquery/04_fct_orders.sql)
-- Grain: one row per transaction.

CREATE OR REPLACE TABLE fct_orders AS
WITH purchase_items AS (
  SELECT *
  FROM stg_events
  WHERE event_name = 'purchase'
    AND transaction_id IS NOT NULL
),

orders AS (
  SELECT
    transaction_id,
    any_value(session_id)            AS session_id,
    any_value(user_id)               AS user_id,
    min(event_timestamp)             AS order_timestamp,
    min(event_date)                  AS order_date,
    any_value(device_category)       AS device_category,
    any_value(country)               AS country,
    any_value(source)                AS source,
    any_value(medium)                AS medium,
    any_value(campaign)              AS campaign,
    any_value(channel_group)         AS channel_group,
    max(purchase_revenue)            AS order_value,
    round(sum(item_revenue), 2)      AS item_revenue_sum,
    sum(quantity)                    AS item_count,
    count(DISTINCT product_id)       AS distinct_products,
    count(DISTINCT product_category) AS distinct_categories,
    list_sort(list(DISTINCT product_category)) AS categories
  FROM purchase_items
  GROUP BY transaction_id
)

SELECT
  o.*,
  -- Order sequence per customer drives repeat purchase and time-to-second-order.
  row_number() OVER (PARTITION BY o.user_id ORDER BY o.order_timestamp)     AS order_seq,
  row_number() OVER (PARTITION BY o.user_id ORDER BY o.order_timestamp) = 1 AS is_first_order,
  date_diff(
    'day',
    lag(o.order_date) OVER (PARTITION BY o.user_id ORDER BY o.order_timestamp),
    o.order_date
  )                                                                         AS days_since_previous_order,
  round(o.order_value / nullif(o.item_count, 0), 2)                         AS avg_item_value,
  extract(hour FROM o.order_timestamp)                                      AS order_hour,
  dayname(o.order_date)                                                     AS order_day_of_week,
  dense_rank() OVER (ORDER BY o.order_value DESC)                           AS order_value_rank
FROM orders AS o;
