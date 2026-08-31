-- dim_users
-- Grain: one row per user_pseudo_id.
-- Acquisition attributes come from the user's first session (first touch), not
-- from the session that converted, so channel quality can be judged on the
-- users a channel actually brought in.

CREATE OR REPLACE TABLE ga4_growth.dim_users AS
WITH session_rollup AS (
  SELECT
    user_id,
    MIN(session_date)                       AS first_seen_date,
    MAX(session_date)                       AS last_seen_date,
    COUNT(DISTINCT session_id)              AS total_sessions,
    COUNT(DISTINCT session_date)            AS active_days,
    SUM(events)                             AS total_events,
    SUM(pageviews)                          AS total_pageviews,
    SUM(view_item_events)                   AS total_product_views,
    SUM(add_to_cart_events)                 AS total_cart_additions,
    SUM(session_duration_sec)               AS total_time_on_site_sec,
    ARRAY_AGG(source        ORDER BY session_start LIMIT 1)[OFFSET(0)] AS acquisition_source,
    ARRAY_AGG(medium        ORDER BY session_start LIMIT 1)[OFFSET(0)] AS acquisition_medium,
    ARRAY_AGG(campaign      ORDER BY session_start LIMIT 1)[OFFSET(0)] AS acquisition_campaign,
    ARRAY_AGG(channel_group ORDER BY session_start LIMIT 1)[OFFSET(0)] AS acquisition_channel,
    ARRAY_AGG(device_category ORDER BY session_start LIMIT 1)[OFFSET(0)] AS first_device,
    ARRAY_AGG(country       ORDER BY session_start LIMIT 1)[OFFSET(0)] AS country
  FROM ga4_growth.fct_sessions
  GROUP BY user_id
),

funnel_rollup AS (
  SELECT
    user_id,
    COUNTIF(added_to_cart)   AS sessions_with_cart,
    COUNTIF(began_checkout)  AS sessions_with_checkout,
    COUNTIF(purchased)       AS sessions_with_purchase
  FROM ga4_growth.fct_funnel
  GROUP BY user_id
),

order_rollup AS (
  SELECT
    user_id,
    COUNT(*)                                        AS total_orders,
    ROUND(SUM(order_value), 2)                      AS total_revenue,
    SUM(item_count)                                 AS total_items_bought,
    MIN(order_date)                                 AS first_purchase_date,
    MAX(order_date)                                 AS last_purchase_date,
    MIN(IF(order_seq = 2, order_date, NULL))        AS second_purchase_date
  FROM ga4_growth.fct_orders
  GROUP BY user_id
)

SELECT
  s.user_id,
  s.first_seen_date,
  s.last_seen_date,
  DATE_TRUNC(s.first_seen_date, WEEK(MONDAY))                          AS acquisition_week,
  DATE_TRUNC(s.first_seen_date, MONTH)                                 AS acquisition_month,
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
  COALESCE(f.sessions_with_cart, 0)                                    AS sessions_with_cart,
  COALESCE(f.sessions_with_checkout, 0)                                AS sessions_with_checkout,
  COALESCE(f.sessions_with_purchase, 0)                                AS sessions_with_purchase,
  COALESCE(o.total_orders, 0)                                          AS total_orders,
  COALESCE(o.total_revenue, 0)                                         AS total_revenue,
  COALESCE(o.total_items_bought, 0)                                    AS total_items_bought,
  o.first_purchase_date,
  o.second_purchase_date,
  o.last_purchase_date,
  ROUND(SAFE_DIVIDE(o.total_revenue, NULLIF(o.total_orders, 0)), 2)    AS average_order_value,
  ROUND(SAFE_DIVIDE(o.total_items_bought, NULLIF(o.total_orders, 0)), 2) AS items_per_order,
  DATE_DIFF(o.first_purchase_date, s.first_seen_date, DAY)             AS days_to_first_purchase,
  DATE_DIFF(o.second_purchase_date, o.first_purchase_date, DAY)        AS days_to_second_purchase,
  DATE_DIFF(s.last_seen_date, s.first_seen_date, DAY) + 1              AS lifespan_days,
  s.total_sessions > 1                                                 AS is_returning_user,
  COALESCE(o.total_orders, 0) > 0                                      AS is_customer,
  COALESCE(o.total_orders, 0) > 1                                      AS is_repeat_customer,
  CASE
    WHEN COALESCE(o.total_orders, 0) > 1                       THEN 'Repeat customer'
    WHEN COALESCE(o.total_orders, 0) = 1                       THEN 'One time customer'
    WHEN COALESCE(f.sessions_with_checkout, 0) > 0             THEN 'Checkout abandoner'
    WHEN COALESCE(f.sessions_with_cart, 0) > 0                 THEN 'Cart abandoner'
    WHEN s.total_product_views > 0                             THEN 'Browser'
    ELSE 'Bounced'
  END                                                                  AS lifecycle_segment
FROM session_rollup AS s
LEFT JOIN funnel_rollup AS f USING (user_id)
LEFT JOIN order_rollup  AS o USING (user_id);
