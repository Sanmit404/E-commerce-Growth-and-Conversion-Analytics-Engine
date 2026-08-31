-- fct_sessions (DuckDB port of sql/bigquery/02_fct_sessions.sql)
-- Grain: one row per session.

CREATE OR REPLACE TABLE fct_sessions AS
WITH deduped AS (
  -- stg_events repeats an event once per item, so collapse back to event grain
  -- before counting anything.
  SELECT
    session_id,
    user_id,
    event_id,
    any_value(event_name)        AS event_name,
    min(event_timestamp)         AS event_timestamp,
    min(event_date)              AS event_date,
    any_value(session_number)    AS session_number,
    any_value(device_category)   AS device_category,
    any_value(operating_system)  AS operating_system,
    any_value(browser)           AS browser,
    any_value(country)           AS country,
    any_value(region)            AS region,
    any_value(source)            AS source,
    any_value(medium)            AS medium,
    any_value(campaign)          AS campaign,
    any_value(channel_group)     AS channel_group,
    any_value(source_medium)     AS source_medium,
    max(engagement_time_msec)    AS engagement_time_msec,
    max(purchase_revenue)        AS purchase_revenue,
    any_value(transaction_id)    AS transaction_id
  FROM stg_events
  GROUP BY session_id, user_id, event_id
),

product_views AS (
  SELECT
    session_id,
    count(DISTINCT product_id)                                              AS products_viewed,
    count(DISTINCT product_id) FILTER (WHERE event_name = 'add_to_cart')     AS products_added,
    avg(price) FILTER (WHERE event_name = 'view_item')                       AS avg_viewed_price,
    list(DISTINCT product_category) FILTER (WHERE product_category IS NOT NULL) AS categories_seen
  FROM stg_events
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
      row_number() OVER (
        PARTITION BY session_id
        ORDER BY count(*) DESC, product_category
      ) AS rn
    FROM stg_events
    WHERE event_name = 'view_item' AND product_category IS NOT NULL
    GROUP BY session_id, product_category
  )
  WHERE rn = 1
),

agg AS (
  SELECT
    session_id,
    user_id,
    min(event_date)                                       AS session_date,
    min(event_timestamp)                                  AS session_start,
    max(event_timestamp)                                  AS session_end,
    date_diff('second', min(event_timestamp), max(event_timestamp)) AS session_duration_sec,
    max(session_number)                                   AS session_number,
    arg_min(device_category, event_timestamp)             AS device_category,
    arg_min(operating_system, event_timestamp)            AS operating_system,
    arg_min(browser, event_timestamp)                     AS browser,
    arg_min(country, event_timestamp)                     AS country,
    arg_min(region, event_timestamp)                      AS region,
    arg_min(source, event_timestamp)                      AS source,
    arg_min(medium, event_timestamp)                      AS medium,
    arg_min(campaign, event_timestamp)                    AS campaign,
    arg_min(channel_group, event_timestamp)               AS channel_group,
    arg_min(source_medium, event_timestamp)               AS source_medium,
    count(*)                                              AS events,
    count(*) FILTER (WHERE event_name = 'page_view')        AS pageviews,
    count(*) FILTER (WHERE event_name = 'view_item')        AS view_item_events,
    count(*) FILTER (WHERE event_name = 'add_to_cart')      AS add_to_cart_events,
    count(*) FILTER (WHERE event_name = 'remove_from_cart') AS remove_from_cart_events,
    count(*) FILTER (WHERE event_name = 'purchase')         AS transactions,
    coalesce(sum(purchase_revenue) FILTER (WHERE event_name = 'purchase'), 0) AS session_revenue,
    sum(coalesce(engagement_time_msec, 0)) / 1000.0       AS engagement_time_sec
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
  a.session_number = 1                                    AS is_first_session,
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
  round(a.session_revenue, 2)                             AS session_revenue,
  a.engagement_time_sec,
  coalesce(p.products_viewed, 0)                          AS products_viewed,
  coalesce(p.products_added, 0)                           AS products_added,
  round(p.avg_viewed_price, 2)                            AS avg_viewed_price,
  coalesce(len(p.categories_seen), 0)                     AS categories_seen,
  t.primary_category,
  dayname(a.session_date)                                 AS day_of_week,
  dayofweek(a.session_date) IN (0, 6)                     AS is_weekend,
  extract(hour FROM a.session_start)                      AS session_hour,
  CASE
    WHEN extract(hour FROM a.session_start) BETWEEN 6 AND 11  THEN 'Morning'
    WHEN extract(hour FROM a.session_start) BETWEEN 12 AND 17 THEN 'Afternoon'
    WHEN extract(hour FROM a.session_start) BETWEEN 18 AND 22 THEN 'Evening'
    ELSE 'Night'
  END                                                     AS day_part
FROM agg AS a
LEFT JOIN product_views AS p USING (session_id)
LEFT JOIN top_category  AS t USING (session_id);
