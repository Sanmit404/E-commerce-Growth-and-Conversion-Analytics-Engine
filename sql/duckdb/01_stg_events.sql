-- stg_events (DuckDB port of sql/bigquery/01_stg_events.sql)
-- raw_events is a view over data/raw/events_*.parquet created by
-- ga4_growth.warehouse. The parquet files carry the same nested schema as the
-- BigQuery export, so the flattening below matches the BigQuery model.
--
-- BigQuery pulls a parameter with a correlated subquery over UNNEST. DuckDB
-- runs that as a nested loop and the model took about three minutes, so the
-- same lookup is done with list_filter instead, which is a few seconds.

CREATE OR REPLACE TABLE stg_events AS
WITH flattened AS (
  SELECT
    strptime(e.event_date, '%Y%m%d')::DATE                    AS event_date,
    make_timestamp(e.event_timestamp)                         AS event_timestamp,
    e.event_name,
    e.user_pseudo_id                                          AS user_id,

    list_filter(e.event_params, p -> p.key = 'ga_session_id')[1].value.int_value        AS ga_session_id,
    list_filter(e.event_params, p -> p.key = 'ga_session_number')[1].value.int_value    AS session_number,
    list_filter(e.event_params, p -> p.key = 'engagement_time_msec')[1].value.int_value AS engagement_time_msec,
    list_filter(e.event_params, p -> p.key = 'page_location')[1].value.string_value     AS page_location,
    list_filter(e.event_params, p -> p.key = 'page_title')[1].value.string_value        AS page_title,

    e.device.category                                         AS device_category,
    e.device.operating_system                                 AS operating_system,
    e.device.web_info.browser                                 AS browser,

    e.geo.country                                             AS country,
    e.geo.region                                              AS region,
    e.geo.city                                                AS city,

    COALESCE(e.traffic_source.source, '(direct)')             AS source,
    COALESCE(e.traffic_source.medium, '(none)')               AS medium,
    COALESCE(e.traffic_source.name, '(not set)')              AS campaign,

    i.item.item_id                                            AS item_id,
    i.item.item_name                                          AS item_name,
    i.item.item_category                                      AS product_category,
    i.item.price                                              AS price,
    i.item.quantity                                           AS quantity,

    e.ecommerce.transaction_id                                AS transaction_id,
    e.ecommerce.purchase_revenue                              AS purchase_revenue,
    e.ecommerce.total_item_quantity                           AS total_item_quantity
  FROM raw_events AS e
  LEFT JOIN LATERAL (SELECT UNNEST(e.items) AS item) AS i ON TRUE
)

SELECT
  md5(user_id || '|' || CAST(epoch_us(event_timestamp) AS VARCHAR) || '|'
      || event_name || '|' || CAST(COALESCE(ga_session_id, 0) AS VARCHAR)) AS event_id,
  user_id || '.' || CAST(COALESCE(ga_session_id, 0) AS VARCHAR)            AS session_id,
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
  source || ' / ' || medium                                   AS source_medium,
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
  dayname(event_date)                                          AS day_of_week
FROM flattened;
