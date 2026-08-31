-- fct_daily_kpis
-- Grain: one row per day. This is the table the executive page of the dashboard
-- reads from, so every headline metric is defined once here instead of being
-- redefined inside Power BI.

CREATE OR REPLACE TABLE ga4_growth.fct_daily_kpis AS
WITH daily AS (
  SELECT
    f.session_date                                              AS event_date,
    COUNT(DISTINCT f.user_id)                                   AS users,
    COUNT(DISTINCT IF(f.session_seq = 1, f.user_id, NULL))      AS new_users,
    COUNT(DISTINCT IF(f.session_seq > 1, f.user_id, NULL))      AS returning_users,
    COUNT(*)                                                    AS sessions,
    COUNTIF(f.viewed_product)                                   AS sessions_with_product_view,
    COUNTIF(f.added_to_cart)                                    AS sessions_with_cart,
    COUNTIF(f.began_checkout)                                   AS sessions_with_checkout,
    COUNTIF(f.purchased)                                        AS sessions_with_purchase,
    SUM(f.pageviews)                                            AS pageviews,
    SUM(f.products_viewed)                                      AS products_viewed
  FROM ga4_growth.fct_funnel AS f
  GROUP BY f.session_date
),

orders AS (
  SELECT
    order_date                     AS event_date,
    COUNT(*)                       AS transactions,
    ROUND(SUM(order_value), 2)     AS revenue,
    SUM(item_count)                AS items_sold,
    COUNTIF(order_seq = 1)         AS first_orders,
    COUNTIF(order_seq > 1)         AS repeat_orders,
    ROUND(SUM(IF(order_seq > 1, order_value, 0)), 2) AS repeat_revenue
  FROM ga4_growth.fct_orders
  GROUP BY order_date
),

joined AS (
  SELECT
    d.event_date,
    d.users,
    d.new_users,
    d.returning_users,
    d.sessions,
    d.sessions_with_product_view,
    d.sessions_with_cart,
    d.sessions_with_checkout,
    d.sessions_with_purchase,
    d.pageviews,
    d.products_viewed,
    COALESCE(o.transactions, 0)   AS transactions,
    COALESCE(o.revenue, 0)        AS revenue,
    COALESCE(o.items_sold, 0)     AS items_sold,
    COALESCE(o.first_orders, 0)   AS first_orders,
    COALESCE(o.repeat_orders, 0)  AS repeat_orders,
    COALESCE(o.repeat_revenue, 0) AS repeat_revenue
  FROM daily AS d
  LEFT JOIN orders AS o USING (event_date)
)

SELECT
  event_date,
  FORMAT_DATE('%A', event_date)                                          AS day_of_week,
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
  ROUND(SAFE_DIVIDE(sessions, NULLIF(users, 0)), 3)                      AS sessions_per_user,
  ROUND(SAFE_DIVIDE(sessions_with_product_view, NULLIF(sessions, 0)), 4) AS product_view_rate,
  ROUND(SAFE_DIVIDE(sessions_with_cart, NULLIF(sessions_with_product_view, 0)), 4) AS view_to_cart_rate,
  ROUND(SAFE_DIVIDE(sessions_with_checkout, NULLIF(sessions_with_cart, 0)), 4)     AS cart_to_checkout_rate,
  ROUND(SAFE_DIVIDE(sessions_with_purchase, NULLIF(sessions_with_checkout, 0)), 4) AS checkout_to_purchase_rate,
  ROUND(SAFE_DIVIDE(sessions_with_purchase, NULLIF(sessions, 0)), 4)     AS session_conversion_rate,
  ROUND(1 - SAFE_DIVIDE(sessions_with_checkout, NULLIF(sessions_with_cart, 0)), 4) AS cart_abandonment_rate,
  ROUND(1 - SAFE_DIVIDE(sessions_with_purchase, NULLIF(sessions_with_checkout, 0)), 4) AS checkout_abandonment_rate,
  ROUND(SAFE_DIVIDE(revenue, NULLIF(transactions, 0)), 2)                AS average_order_value,
  ROUND(SAFE_DIVIDE(revenue, NULLIF(users, 0)), 2)                       AS revenue_per_user,
  ROUND(SAFE_DIVIDE(revenue, NULLIF(sessions, 0)), 2)                    AS revenue_per_session,
  ROUND(SAFE_DIVIDE(items_sold, NULLIF(transactions, 0)), 2)             AS items_per_order,
  ROUND(SAFE_DIVIDE(repeat_revenue, NULLIF(revenue, 0)), 4)              AS repeat_revenue_share,
  -- Trailing averages smooth the weekday cycle; LAG gives week on week growth.
  ROUND(AVG(revenue) OVER (ORDER BY event_date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW), 2) AS revenue_7d_avg,
  ROUND(AVG(sessions) OVER (ORDER BY event_date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW), 1) AS sessions_7d_avg,
  ROUND(SAFE_DIVIDE(revenue, NULLIF(LAG(revenue, 7) OVER (ORDER BY event_date), 0)) - 1, 4)   AS revenue_wow_growth,
  ROUND(SAFE_DIVIDE(users, NULLIF(LAG(users, 7) OVER (ORDER BY event_date), 0)) - 1, 4)       AS users_wow_growth,
  ROUND(SAFE_DIVIDE(new_users, NULLIF(LAG(new_users, 7) OVER (ORDER BY event_date), 0)) - 1, 4) AS new_users_wow_growth
FROM joined;
