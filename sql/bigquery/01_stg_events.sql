-- stg_events
-- Grain: one row per event, plus one row per item on events that carry items.
-- event_id keeps the true event grain recoverable with COUNT(DISTINCT event_id).
--
-- Source: the public GA4 export of the Google Merchandise Store. The sample
-- covers 2020-11-01 to 2021-01-31, so every model is scoped to that window.

CREATE SCHEMA IF NOT EXISTS ga4_growth;

CREATE OR REPLACE TABLE ga4_growth.stg_events AS
WITH raw_events AS (
  SELECT *
  FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
  WHERE _TABLE_SUFFIX BETWEEN '20201101' AND '20210131'
),

flattened AS (
  SELECT
    PARSE_DATE('%Y%m%d', e.event_date)                        AS event_date,
    TIMESTAMP_MICROS(e.event_timestamp)                       AS event_timestamp,
    e.event_name,
    e.user_pseudo_id                                          AS user_id,

    (SELECT value.int_value FROM UNNEST(e.event_params)
      WHERE key = 'ga_session_id')                            AS ga_session_id,
    (SELECT value.int_value FROM UNNEST(e.event_params)
      WHERE key = 'ga_session_number')                        AS session_number,
    (SELECT value.int_value FROM UNNEST(e.event_params)
      WHERE key = 'engagement_time_msec')                     AS engagement_time_msec,
    (SELECT value.string_value FROM UNNEST(e.event_params)
      WHERE key = 'page_location')                            AS page_location,
    (SELECT value.string_value FROM UNNEST(e.event_params)
      WHERE key = 'page_title')                               AS page_title,

    e.device.category                                         AS device_category,
    e.device.operating_system                                 AS operating_system,
    e.device.web_info.browser                                 AS browser,

    e.geo.country                                             AS country,
    e.geo.region                                              AS region,
    e.geo.city                                                AS city,

    COALESCE(e.traffic_source.source, '(direct)')             AS source,
    COALESCE(e.traffic_source.medium, '(none)')               AS medium,
    COALESCE(e.traffic_source.name, '(not set)')              AS campaign,

    item.item_id,
    item.item_name,
    item.item_category                                        AS product_category,
    item.price,
    item.quantity,

    e.ecommerce.transaction_id,
    e.ecommerce.purchase_revenue,
    e.ecommerce.total_item_quantity
  FROM raw_events AS e
  LEFT JOIN UNNEST(e.items) AS item
)

SELECT
  TO_HEX(MD5(CONCAT(
    user_id, '|', CAST(UNIX_MICROS(event_timestamp) AS STRING), '|',
    event_name, '|', CAST(COALESCE(ga_session_id, 0) AS STRING)
  )))                                                         AS event_id,
  CONCAT(user_id, '.', CAST(COALESCE(ga_session_id, 0) AS STRING)) AS session_id,
  event_date,
  event_timestamp,
  event_name,
  user_id,
  ga_session_id,
  session_number,
  engagement_time_msec,
  page_location,
  page_title,
  device_category,
  operating_system,
  browser,
  country,
  region,
  city,
  source,
  medium,
  campaign,
  CONCAT(source, ' / ', medium)                               AS source_medium,
  CASE
    WHEN medium IN ('cpc', 'ppc', 'paid_social', 'display') THEN 'Paid'
    WHEN medium = 'organic'                                  THEN 'Organic Search'
    WHEN medium = 'referral'                                 THEN 'Referral'
    WHEN medium = 'email'                                    THEN 'Email'
    WHEN medium = 'affiliate'                                THEN 'Affiliate'
    WHEN source = '(direct)'                                 THEN 'Direct'
    ELSE 'Other'
  END                                                          AS channel_group,
  item_id                                                      AS product_id,
  item_name                                                    AS product_name,
  product_category,
  price,
  quantity,
  price * COALESCE(quantity, 0)                                AS item_revenue,
  transaction_id,
  purchase_revenue,
  total_item_quantity,
  EXTRACT(HOUR FROM event_timestamp)                           AS event_hour,
  FORMAT_DATE('%A', event_date)                                AS day_of_week
FROM flattened;
