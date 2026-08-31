-- fct_daily_kpis (DuckDB port of sql/bigquery/07_fct_daily_kpis.sql)
-- Grain: one row per day. Every headline metric is defined once here so the
-- dashboard and the notebooks cannot drift apart.

CREATE OR REPLACE TABLE fct_daily_kpis AS
WITH daily AS (
  SELECT
    f.session_date                                          AS event_date,
    count(DISTINCT f.user_id)                               AS users,
    count(DISTINCT f.user_id) FILTER (WHERE f.session_seq = 1) AS new_users,
    count(DISTINCT f.user_id) FILTER (WHERE f.session_seq > 1) AS returning_users,
    count(*)                                                AS sessions,
    count(*) FILTER (WHERE f.viewed_product)                AS sessions_with_product_view,
    count(*) FILTER (WHERE f.added_to_cart)                 AS sessions_with_cart,
    count(*) FILTER (WHERE f.began_checkout)                AS sessions_with_checkout,
    count(*) FILTER (WHERE f.purchased)                     AS sessions_with_purchase,
    sum(f.pageviews)                                        AS pageviews,
    sum(f.products_viewed)                                  AS products_viewed
  FROM fct_funnel AS f
  GROUP BY f.session_date
),

orders AS (
  SELECT
    order_date                  AS event_date,
    count(*)                    AS transactions,
    round(sum(order_value), 2)  AS revenue,
    sum(item_count)             AS items_sold,
    count(*) FILTER (WHERE order_seq = 1) AS first_orders,
    count(*) FILTER (WHERE order_seq > 1) AS repeat_orders,
    round(coalesce(sum(order_value) FILTER (WHERE order_seq > 1), 0), 2) AS repeat_revenue
  FROM fct_orders
  GROUP BY order_date
),

joined AS (
  SELECT
    d.*,
    coalesce(o.transactions, 0)   AS transactions,
    coalesce(o.revenue, 0)        AS revenue,
    coalesce(o.items_sold, 0)     AS items_sold,
    coalesce(o.first_orders, 0)   AS first_orders,
    coalesce(o.repeat_orders, 0)  AS repeat_orders,
    coalesce(o.repeat_revenue, 0) AS repeat_revenue
  FROM daily AS d
  LEFT JOIN orders AS o USING (event_date)
)

SELECT
  event_date,
  dayname(event_date)                                                     AS day_of_week,
  users,
  new_users,
  returning_users,
  sessions,
  transactions,
  revenue,
  items_sold,
  first_orders,
  repeat_orders,
  repeat_revenue,
  round(sessions / nullif(users, 0), 3)                                   AS sessions_per_user,
  round(sessions_with_product_view / nullif(sessions, 0), 4)              AS product_view_rate,
  round(sessions_with_cart / nullif(sessions_with_product_view, 0), 4)    AS view_to_cart_rate,
  round(sessions_with_checkout / nullif(sessions_with_cart, 0), 4)        AS cart_to_checkout_rate,
  round(sessions_with_purchase / nullif(sessions_with_checkout, 0), 4)    AS checkout_to_purchase_rate,
  round(sessions_with_purchase / nullif(sessions, 0), 4)                  AS session_conversion_rate,
  round(1 - sessions_with_checkout / nullif(sessions_with_cart, 0), 4)    AS cart_abandonment_rate,
  round(1 - sessions_with_purchase / nullif(sessions_with_checkout, 0), 4) AS checkout_abandonment_rate,
  round(revenue / nullif(transactions, 0), 2)                             AS average_order_value,
  round(revenue / nullif(users, 0), 2)                                    AS revenue_per_user,
  round(revenue / nullif(sessions, 0), 2)                                 AS revenue_per_session,
  round(items_sold / nullif(transactions, 0), 2)                          AS items_per_order,
  round(repeat_revenue / nullif(revenue, 0), 4)                           AS repeat_revenue_share,
  -- Trailing averages smooth the weekday cycle; LAG gives week on week growth.
  round(avg(revenue) OVER (ORDER BY event_date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW), 2)  AS revenue_7d_avg,
  round(avg(sessions) OVER (ORDER BY event_date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW), 1) AS sessions_7d_avg,
  round(revenue / nullif(lag(revenue, 7) OVER (ORDER BY event_date), 0) - 1, 4)     AS revenue_wow_growth,
  round(users / nullif(lag(users, 7) OVER (ORDER BY event_date), 0) - 1, 4)         AS users_wow_growth,
  round(new_users / nullif(lag(new_users, 7) OVER (ORDER BY event_date), 0) - 1, 4) AS new_users_wow_growth
FROM joined;
