-- fct_sessions
-- Grain: one row per session.
-- Session attributes are taken from the first event of the session so a session
-- that changes source mid-way is still attributed to how it started.

CREATE OR REPLACE TABLE ga4_growth.fct_sessions AS
WITH events AS (
  SELECT * FROM ga4_growth.stg_events
),

deduped AS (
  -- stg_events repeats an event once per item, so collapse back to event grain
  -- before counting anything.
  SELECT
    session_id,
    user_id,
    event_id,
    ANY_VALUE(event_name)      AS event_name,
    MIN(event_timestamp)       AS event_timestamp,
    MIN(event_date)            AS event_date,
    ANY_VALUE(session_number)  AS session_number,
    ANY_VALUE(device_category) AS device_category,
    ANY_VALUE(operating_system) AS operating_system,
    ANY_VALUE(browser)         AS browser,
    ANY_VALUE(country)         AS country,
    ANY_VALUE(region)          AS region,
    ANY_VALUE(source)          AS source,
    ANY_VALUE(medium)          AS medium,
    ANY_VALUE(campaign)        AS campaign,
    ANY_VALUE(channel_group)   AS channel_group,
    ANY_VALUE(source_medium)   AS source_medium,
    MAX(engagement_time_msec)  AS engagement_time_msec,
    MAX(purchase_revenue)      AS purchase_revenue,
    ANY_VALUE(transaction_id)  AS transaction_id
  FROM events
  GROUP BY session_id, user_id, event_id
),

product_views AS (
  SELECT
    session_id,
    COUNT(DISTINCT product_id)                                   AS products_viewed,
    COUNT(DISTINCT IF(event_name = 'add_to_cart', product_id, NULL)) AS products_added,
    AVG(IF(event_name = 'view_item', price, NULL))               AS avg_viewed_price,
    ARRAY_AGG(DISTINCT product_category IGNORE NULLS)            AS categories_seen
  FROM events
  WHERE product_id IS NOT NULL
  GROUP BY session_id
),

top_category AS (
  -- The category a session spent most of its product views on.
  SELECT session_id, product_category AS primary_category
  FROM (
    SELECT
      session_id,
      product_category,
      ROW_NUMBER() OVER (
        PARTITION BY session_id
        ORDER BY COUNT(*) DESC, product_category
      ) AS rn
    FROM events
    WHERE event_name = 'view_item' AND product_category IS NOT NULL
    GROUP BY session_id, product_category
  )
  WHERE rn = 1
),

agg AS (
  SELECT
    session_id,
    user_id,
    MIN(event_date)                                              AS session_date,
    MIN(event_timestamp)                                         AS session_start,
    MAX(event_timestamp)                                         AS session_end,
    TIMESTAMP_DIFF(MAX(event_timestamp), MIN(event_timestamp), SECOND) AS session_duration_sec,
    MAX(session_number)                                          AS session_number,
    ARRAY_AGG(device_category ORDER BY event_timestamp LIMIT 1)[OFFSET(0)]  AS device_category,
    ARRAY_AGG(operating_system ORDER BY event_timestamp LIMIT 1)[OFFSET(0)] AS operating_system,
    ARRAY_AGG(browser ORDER BY event_timestamp LIMIT 1)[OFFSET(0)]          AS browser,
    ARRAY_AGG(country ORDER BY event_timestamp LIMIT 1)[OFFSET(0)]          AS country,
    ARRAY_AGG(region ORDER BY event_timestamp LIMIT 1)[OFFSET(0)]           AS region,
    ARRAY_AGG(source ORDER BY event_timestamp LIMIT 1)[OFFSET(0)]           AS source,
    ARRAY_AGG(medium ORDER BY event_timestamp LIMIT 1)[OFFSET(0)]           AS medium,
    ARRAY_AGG(campaign ORDER BY event_timestamp LIMIT 1)[OFFSET(0)]         AS campaign,
    ARRAY_AGG(channel_group ORDER BY event_timestamp LIMIT 1)[OFFSET(0)]    AS channel_group,
    ARRAY_AGG(source_medium ORDER BY event_timestamp LIMIT 1)[OFFSET(0)]    AS source_medium,
    COUNT(*)                                                     AS events,
    COUNTIF(event_name = 'page_view')                            AS pageviews,
    COUNTIF(event_name = 'view_item')                            AS view_item_events,
    COUNTIF(event_name = 'add_to_cart')                          AS add_to_cart_events,
    COUNTIF(event_name = 'remove_from_cart')                     AS remove_from_cart_events,
    COUNTIF(event_name = 'purchase')                             AS transactions,
    SUM(IF(event_name = 'purchase', purchase_revenue, 0))        AS session_revenue,
    SUM(COALESCE(engagement_time_msec, 0)) / 1000.0              AS engagement_time_sec
  FROM deduped
  GROUP BY session_id, user_id
)

SELECT
  a.session_id,
  a.user_id,
  a.session_date,
  a.session_start,
  a.session_end,
  a.session_duration_sec,
  a.session_number,
  a.session_number = 1                                           AS is_first_session,
  a.device_category,
  a.operating_system,
  a.browser,
  a.country,
  a.region,
  a.source,
  a.medium,
  a.campaign,
  a.channel_group,
  a.source_medium,
  a.events,
  a.pageviews,
  a.view_item_events,
  a.add_to_cart_events,
  a.remove_from_cart_events,
  a.transactions,
  ROUND(a.session_revenue, 2)                                    AS session_revenue,
  a.engagement_time_sec,
  COALESCE(p.products_viewed, 0)                                 AS products_viewed,
  COALESCE(p.products_added, 0)                                  AS products_added,
  ROUND(p.avg_viewed_price, 2)                                   AS avg_viewed_price,
  ARRAY_LENGTH(COALESCE(p.categories_seen, []))                  AS categories_seen,
  t.primary_category,
  FORMAT_DATE('%A', a.session_date)                              AS day_of_week,
  EXTRACT(DAYOFWEEK FROM a.session_date) IN (1, 7)               AS is_weekend,
  EXTRACT(HOUR FROM a.session_start)                             AS session_hour,
  CASE
    WHEN EXTRACT(HOUR FROM a.session_start) BETWEEN 6 AND 11  THEN 'Morning'
    WHEN EXTRACT(HOUR FROM a.session_start) BETWEEN 12 AND 17 THEN 'Afternoon'
    WHEN EXTRACT(HOUR FROM a.session_start) BETWEEN 18 AND 22 THEN 'Evening'
    ELSE 'Night'
  END                                                            AS day_part
FROM agg AS a
LEFT JOIN product_views AS p USING (session_id)
LEFT JOIN top_category  AS t USING (session_id);
