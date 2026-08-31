-- fct_funnel
-- Grain: one row per session, with a flag for every funnel step and the
-- segment columns the analysis slices on.
-- Step flags are cumulative by definition: a session that reached checkout also
-- viewed a product, so downstream conversion rates are never above 100%.

CREATE OR REPLACE TABLE ga4_growth.fct_funnel AS
WITH step_events AS (
  SELECT
    session_id,
    user_id,
    MIN(IF(event_name = 'view_item',         event_timestamp, NULL)) AS ts_view_item,
    MIN(IF(event_name = 'add_to_cart',       event_timestamp, NULL)) AS ts_add_to_cart,
    MIN(IF(event_name = 'view_cart',         event_timestamp, NULL)) AS ts_view_cart,
    MIN(IF(event_name = 'begin_checkout',    event_timestamp, NULL)) AS ts_begin_checkout,
    MIN(IF(event_name = 'add_shipping_info', event_timestamp, NULL)) AS ts_add_shipping,
    MIN(IF(event_name = 'add_payment_info',  event_timestamp, NULL)) AS ts_add_payment,
    MIN(IF(event_name = 'purchase',          event_timestamp, NULL)) AS ts_purchase
  FROM ga4_growth.stg_events
  GROUP BY session_id, user_id
),

flags AS (
  SELECT
    session_id,
    user_id,
    ts_view_item IS NOT NULL                                       AS viewed_product,
    ts_add_to_cart IS NOT NULL                                     AS added_to_cart,
    ts_view_cart IS NOT NULL                                       AS viewed_cart,
    ts_begin_checkout IS NOT NULL                                  AS began_checkout,
    ts_add_shipping IS NOT NULL                                    AS added_shipping,
    ts_add_payment IS NOT NULL                                     AS added_payment,
    ts_purchase IS NOT NULL                                        AS purchased,
    TIMESTAMP_DIFF(ts_add_to_cart, ts_view_item, SECOND)           AS sec_view_to_cart,
    TIMESTAMP_DIFF(ts_begin_checkout, ts_add_to_cart, SECOND)      AS sec_cart_to_checkout,
    TIMESTAMP_DIFF(ts_add_payment, ts_add_shipping, SECOND)        AS sec_shipping_to_payment,
    TIMESTAMP_DIFF(ts_purchase, ts_begin_checkout, SECOND)         AS sec_checkout_to_purchase
  FROM step_events
),

session_context AS (
  SELECT
    s.*,
    -- Window functions over the user's session history give the returning-user
    -- view without a self join.
    LAG(s.session_date) OVER (PARTITION BY s.user_id ORDER BY s.session_start) AS previous_session_date,
    ROW_NUMBER() OVER (PARTITION BY s.user_id ORDER BY s.session_start)        AS session_seq,
    COUNT(*) OVER (PARTITION BY s.user_id)                                     AS user_total_sessions
  FROM ga4_growth.fct_sessions AS s
)

SELECT
  c.session_id,
  c.user_id,
  c.session_date,
  c.session_seq,
  c.user_total_sessions,
  DATE_DIFF(c.session_date, c.previous_session_date, DAY)          AS days_since_previous_session,
  IF(c.session_seq = 1, 'New', 'Returning')                        AS user_type,
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
  END                                                              AS price_band,
  TRUE                                                             AS session_started,
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
  END                                                              AS furthest_step,
  CASE
    WHEN f.purchased        THEN '7 Purchase'
    WHEN f.added_payment    THEN '6 Payment info'
    WHEN f.added_shipping   THEN '5 Shipping info'
    WHEN f.began_checkout   THEN '4 Begin checkout'
    WHEN f.viewed_cart      THEN '3 View cart'
    WHEN f.added_to_cart    THEN '2 Add to cart'
    WHEN f.viewed_product   THEN '1 Product view'
    ELSE '0 Session only'
  END                                                              AS furthest_step_name,
  c.session_revenue
FROM session_context AS c
JOIN flags AS f USING (session_id, user_id);
