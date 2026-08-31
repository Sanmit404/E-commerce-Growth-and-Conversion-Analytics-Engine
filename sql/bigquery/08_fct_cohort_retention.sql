-- fct_cohort_retention
-- Grain: acquisition week x acquisition channel x weeks since acquisition.
-- weeks_observed says how much history a cohort actually has, so the analysis
-- can drop the cells that are only young rather than genuinely bad.

CREATE OR REPLACE TABLE ga4_growth.fct_cohort_retention AS
WITH cohorts AS (
  SELECT
    user_id,
    acquisition_week,
    acquisition_channel,
    first_seen_date
  FROM ga4_growth.dim_users
),

activity AS (
  SELECT DISTINCT
    user_id,
    DATE_TRUNC(session_date, WEEK(MONDAY)) AS activity_week
  FROM ga4_growth.fct_sessions
),

order_activity AS (
  SELECT
    user_id,
    DATE_TRUNC(order_date, WEEK(MONDAY)) AS activity_week,
    COUNT(*)                             AS orders,
    SUM(order_value)                     AS revenue
  FROM ga4_growth.fct_orders
  GROUP BY user_id, activity_week
),

cohort_size AS (
  SELECT
    acquisition_week,
    acquisition_channel,
    COUNT(DISTINCT user_id) AS cohort_users
  FROM cohorts
  GROUP BY acquisition_week, acquisition_channel
),

joined AS (
  SELECT
    c.acquisition_week,
    c.acquisition_channel,
    DATE_DIFF(a.activity_week, c.acquisition_week, WEEK(MONDAY)) AS week_index,
    COUNT(DISTINCT c.user_id)                                    AS active_users,
    COUNT(DISTINCT IF(o.orders > 0, c.user_id, NULL))            AS purchasing_users,
    COALESCE(SUM(o.orders), 0)                                   AS orders,
    ROUND(COALESCE(SUM(o.revenue), 0), 2)                        AS revenue
  FROM cohorts AS c
  JOIN activity AS a USING (user_id)
  LEFT JOIN order_activity AS o
    ON o.user_id = c.user_id AND o.activity_week = a.activity_week
  GROUP BY c.acquisition_week, c.acquisition_channel, week_index
)

SELECT
  j.acquisition_week,
  j.acquisition_channel,
  j.week_index,
  s.cohort_users,
  j.active_users,
  j.purchasing_users,
  j.orders,
  j.revenue,
  ROUND(SAFE_DIVIDE(j.active_users, NULLIF(s.cohort_users, 0)), 4)     AS retention_rate,
  ROUND(SAFE_DIVIDE(j.purchasing_users, NULLIF(s.cohort_users, 0)), 4) AS purchase_rate,
  ROUND(SAFE_DIVIDE(j.revenue, NULLIF(s.cohort_users, 0)), 2)          AS revenue_per_cohort_user,
  DATE_DIFF(
    (SELECT MAX(session_date) FROM ga4_growth.fct_sessions),
    j.acquisition_week,
    WEEK(MONDAY)
  )                                                                    AS weeks_observed
FROM joined AS j
JOIN cohort_size AS s USING (acquisition_week, acquisition_channel)
WHERE j.week_index >= 0;
