-- dim_users (DuckDB port of sql/bigquery/06_dim_users.sql)
-- Grain: one row per user_pseudo_id.

CREATE OR REPLACE TABLE dim_users AS
WITH session_rollup AS (
  SELECT
    user_id,
    min(session_date)                          AS first_seen_date,
    max(session_date)                          AS last_seen_date,
    count(DISTINCT session_id)                 AS total_sessions,
    count(DISTINCT session_date)               AS active_days,
    sum(events)                                AS total_events,
    sum(pageviews)                             AS total_pageviews,
    sum(view_item_events)                      AS total_product_views,
    sum(add_to_cart_events)                    AS total_cart_additions,
    sum(session_duration_sec)                  AS total_time_on_site_sec,
    arg_min(source, session_start)             AS acquisition_source,
    arg_min(medium, session_start)             AS acquisition_medium,
    arg_min(campaign, session_start)           AS acquisition_campaign,
    arg_min(channel_group, session_start)      AS acquisition_channel,
    arg_min(device_category, session_start)    AS first_device,
    arg_min(country, session_start)            AS country
  FROM fct_sessions
  GROUP BY user_id
),

funnel_rollup AS (
  SELECT
    user_id,
    count(*) FILTER (WHERE added_to_cart)  AS sessions_with_cart,
    count(*) FILTER (WHERE began_checkout) AS sessions_with_checkout,
    count(*) FILTER (WHERE purchased)      AS sessions_with_purchase
  FROM fct_funnel
  GROUP BY user_id
),

order_rollup AS (
  SELECT
    user_id,
    count(*)                                     AS total_orders,
    round(sum(order_value), 2)                   AS total_revenue,
    sum(item_count)                              AS total_items_bought,
    min(order_date)                              AS first_purchase_date,
    max(order_date)                              AS last_purchase_date,
    min(order_date) FILTER (WHERE order_seq = 2) AS second_purchase_date
  FROM fct_orders
  GROUP BY user_id
)

SELECT
  s.user_id,
  s.first_seen_date,
  s.last_seen_date,
  date_trunc('week', s.first_seen_date)                        AS acquisition_week,
  date_trunc('month', s.first_seen_date)                       AS acquisition_month,
  s.acquisition_source,
  s.acquisition_medium,
  s.acquisition_campaign,
  s.acquisition_channel,
  s.first_device,
  s.country,
  s.total_sessions,
  s.active_days,
  s.total_events,
  s.total_pageviews,
  s.total_product_views,
  s.total_cart_additions,
  s.total_time_on_site_sec,
  coalesce(f.sessions_with_cart, 0)                            AS sessions_with_cart,
  coalesce(f.sessions_with_checkout, 0)                        AS sessions_with_checkout,
  coalesce(f.sessions_with_purchase, 0)                        AS sessions_with_purchase,
  coalesce(o.total_orders, 0)                                  AS total_orders,
  coalesce(o.total_revenue, 0)                                 AS total_revenue,
  coalesce(o.total_items_bought, 0)                            AS total_items_bought,
  o.first_purchase_date,
  o.second_purchase_date,
  o.last_purchase_date,
  round(o.total_revenue / nullif(o.total_orders, 0), 2)        AS average_order_value,
  round(o.total_items_bought / nullif(o.total_orders, 0), 2)   AS items_per_order,
  date_diff('day', s.first_seen_date, o.first_purchase_date)   AS days_to_first_purchase,
  date_diff('day', o.first_purchase_date, o.second_purchase_date) AS days_to_second_purchase,
  date_diff('day', s.first_seen_date, s.last_seen_date) + 1    AS lifespan_days,
  s.total_sessions > 1                                         AS is_returning_user,
  coalesce(o.total_orders, 0) > 0                              AS is_customer,
  coalesce(o.total_orders, 0) > 1                              AS is_repeat_customer,
  CASE
    WHEN coalesce(o.total_orders, 0) > 1           THEN 'Repeat customer'
    WHEN coalesce(o.total_orders, 0) = 1           THEN 'One time customer'
    WHEN coalesce(f.sessions_with_checkout, 0) > 0 THEN 'Checkout abandoner'
    WHEN coalesce(f.sessions_with_cart, 0) > 0     THEN 'Cart abandoner'
    WHEN s.total_product_views > 0                 THEN 'Browser'
    ELSE 'Bounced'
  END                                                          AS lifecycle_segment
FROM session_rollup AS s
LEFT JOIN funnel_rollup AS f USING (user_id)
LEFT JOIN order_rollup  AS o USING (user_id);
