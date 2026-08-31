-- fct_cohort_retention (DuckDB port of sql/bigquery/08_fct_cohort_retention.sql)
-- Grain: acquisition week x acquisition channel x weeks since acquisition.

CREATE OR REPLACE TABLE fct_cohort_retention AS
WITH cohorts AS (
  SELECT
    user_id,
    acquisition_week,
    acquisition_channel,
    first_seen_date
  FROM dim_users
),

activity AS (
  SELECT DISTINCT
    user_id,
    date_trunc('week', session_date) AS activity_week
  FROM fct_sessions
),

order_activity AS (
  SELECT
    user_id,
    date_trunc('week', order_date) AS activity_week,
    count(*)                       AS orders,
    sum(order_value)               AS revenue
  FROM fct_orders
  GROUP BY user_id, activity_week
),

cohort_size AS (
  SELECT
    acquisition_week,
    acquisition_channel,
    count(DISTINCT user_id) AS cohort_users
  FROM cohorts
  GROUP BY acquisition_week, acquisition_channel
),

joined AS (
  SELECT
    c.acquisition_week,
    c.acquisition_channel,
    date_diff('week', c.acquisition_week, a.activity_week)  AS week_index,
    count(DISTINCT c.user_id)                               AS active_users,
    count(DISTINCT c.user_id) FILTER (WHERE o.orders > 0)   AS purchasing_users,
    coalesce(sum(o.orders), 0)                              AS orders,
    round(coalesce(sum(o.revenue), 0), 2)                   AS revenue
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
  round(j.active_users / nullif(s.cohort_users, 0), 4)     AS retention_rate,
  round(j.purchasing_users / nullif(s.cohort_users, 0), 4) AS purchase_rate,
  round(j.revenue / nullif(s.cohort_users, 0), 2)          AS revenue_per_cohort_user,
  date_diff('week', j.acquisition_week, (SELECT max(session_date) FROM fct_sessions)) AS weeks_observed
FROM joined AS j
JOIN cohort_size AS s USING (acquisition_week, acquisition_channel)
WHERE j.week_index >= 0;
