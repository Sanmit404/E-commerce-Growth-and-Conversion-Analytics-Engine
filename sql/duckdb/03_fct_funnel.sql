-- fct_funnel (DuckDB port of sql/bigquery/03_fct_funnel.sql)
-- Grain: one row per session, one flag per funnel step.

CREATE OR REPLACE TABLE fct_funnel AS
WITH step_events AS (
  SELECT
    session_id,
    user_id,
    min(event_timestamp) FILTER (WHERE event_name = 'view_item')         AS ts_view_item,
    min(event_timestamp) FILTER (WHERE event_name = 'add_to_cart')       AS ts_add_to_cart,
    min(event_timestamp) FILTER (WHERE event_name = 'view_cart')         AS ts_view_cart,
    min(event_timestamp) FILTER (WHERE event_name = 'begin_checkout')    AS ts_begin_checkout,
    min(event_timestamp) FILTER (WHERE event_name = 'add_shipping_info') AS ts_add_shipping,
    min(event_timestamp) FILTER (WHERE event_name = 'add_payment_info')  AS ts_add_payment,
    min(event_timestamp) FILTER (WHERE event_name = 'purchase')          AS ts_purchase
  FROM stg_events
  GROUP BY session_id, user_id
),

flags AS (
  SELECT
    session_id,
    user_id,
    ts_view_item IS NOT NULL                                              AS viewed_product,
    ts_add_to_cart IS NOT NULL                                            AS added_to_cart,
    ts_view_cart IS NOT NULL                                              AS viewed_cart,
    ts_begin_checkout IS NOT NULL                                         AS began_checkout,
    ts_add_shipping IS NOT NULL                                           AS added_shipping,
    ts_add_payment IS NOT NULL                                            AS added_payment,
    ts_purchase IS NOT NULL                                               AS purchased,
    date_diff('second', ts_view_item, ts_add_to_cart)                     AS sec_view_to_cart,
    date_diff('second', ts_add_to_cart, ts_begin_checkout)                AS sec_cart_to_checkout,
    date_diff('second', ts_add_shipping, ts_add_payment)                  AS sec_shipping_to_payment,
    date_diff('second', ts_begin_checkout, ts_purchase)                   AS sec_checkout_to_purchase
  FROM step_events
),

session_context AS (
  SELECT
    s.*,
    -- Window functions over the user's session history give the returning-user
    -- view without a self join.
    lag(s.session_date) OVER (PARTITION BY s.user_id ORDER BY s.session_start) AS previous_session_date,
    row_number() OVER (PARTITION BY s.user_id ORDER BY s.session_start)        AS session_seq,
    count(*) OVER (PARTITION BY s.user_id)                                     AS user_total_sessions
  FROM fct_sessions AS s
)

SELECT
  c.session_id,
  c.user_id,
  c.session_date,
  c.session_seq,
  c.user_total_sessions,
  date_diff('day', c.previous_session_date, c.session_date)     AS days_since_previous_session,
  CASE WHEN c.session_seq = 1 THEN 'New' ELSE 'Returning' END   AS user_type,
  c.device_category,
  c.operating_system,
  c.browser,
  c.country,
  c.source,
  c.medium,
  c.campaign,
  c.channel_group,
  c.source_medium,
  c.primary_category,
  c.day_of_week,
  c.is_weekend,
  c.session_hour,
  c.day_part,
  c.session_duration_sec,
  c.pageviews,
  c.products_viewed,
  c.avg_viewed_price,
  CASE
    WHEN c.avg_viewed_price IS NULL     THEN 'No product view'
    WHEN c.avg_viewed_price < 15        THEN '1. Under $15'
    WHEN c.avg_viewed_price < 30        THEN '2. $15-30'
    WHEN c.avg_viewed_price < 60        THEN '3. $30-60'
    WHEN c.avg_viewed_price < 100       THEN '4. $60-100'
    ELSE '5. $100+'
  END                                                           AS price_band,
  TRUE                                                          AS session_started,
  f.viewed_product,
  f.added_to_cart,
  f.viewed_cart,
  f.began_checkout,
  f.added_shipping,
  f.added_payment,
  f.purchased,
  f.sec_view_to_cart,
  f.sec_cart_to_checkout,
  f.sec_shipping_to_payment,
  f.sec_checkout_to_purchase,
  CASE
    WHEN f.purchased        THEN 7
    WHEN f.added_payment    THEN 6
    WHEN f.added_shipping   THEN 5
    WHEN f.began_checkout   THEN 4
    WHEN f.viewed_cart      THEN 3
    WHEN f.added_to_cart    THEN 2
    WHEN f.viewed_product   THEN 1
    ELSE 0
  END                                                           AS furthest_step,
  CASE
    WHEN f.purchased        THEN '7 Purchase'
    WHEN f.added_payment    THEN '6 Payment info'
    WHEN f.added_shipping   THEN '5 Shipping info'
    WHEN f.began_checkout   THEN '4 Begin checkout'
    WHEN f.viewed_cart      THEN '3 View cart'
    WHEN f.added_to_cart    THEN '2 Add to cart'
    WHEN f.viewed_product   THEN '1 Product view'
    ELSE '0 Session only'
  END                                                           AS furthest_step_name,
  c.session_revenue
FROM session_context AS c
JOIN flags AS f USING (session_id, user_id);
