# Metric definitions

Every metric is defined once, in `src/ga4_growth/metrics.py`. The notebooks, the
Streamlit app and the Power BI extract all call the same functions, so a number
cannot mean two things in two places.

## Grain

The funnel is measured on sessions. A user who browses on Monday and buys on
Thursday has two sessions, and only the Thursday one counts as converted. A user
level funnel would hide which visit broke, and it would also make the funnel
non comparable to the checkout flow, which is a single sitting.

A session is a GA4 `ga_session_id` for a `user_pseudo_id`. Sessions that cross
midnight are attributed to the day they started.

Steps are cumulative. A session counted at Begin checkout is also counted at Add
to cart, even if the events did not arrive in that order. This matters because
GA4 sometimes delivers events out of order, and because a user can start
checkout from a saved cart without adding anything in that session. The model in
`03_fct_funnel.sql` sets each flag as "this step or any later step happened".

## Funnel steps

| Step | Event | Column |
| --- | --- | --- |
| Session | any event | session_started |
| Product view | view_item | viewed_product |
| Add to cart | add_to_cart | added_to_cart |
| View cart | view_cart | viewed_cart |
| Begin checkout | begin_checkout | began_checkout |
| Shipping info | add_shipping_info | added_shipping |
| Payment info | add_payment_info | added_payment |
| Purchase | purchase | purchased |

## Rates

| Metric | Definition |
| --- | --- |
| Product view rate | sessions with a product view / all sessions |
| View to cart | sessions with an add to cart / sessions with a product view |
| Cart to checkout | sessions that began checkout / sessions with an add to cart |
| Shipping to payment | sessions with payment info / sessions with shipping info |
| Checkout to purchase | sessions that purchased / sessions that began checkout |
| Session conversion rate | sessions that purchased / all sessions |
| Cart abandonment rate | 1 minus cart to checkout |
| Checkout abandonment rate | 1 minus checkout to purchase |

Two things to watch. View to cart uses product view sessions as the denominator,
not all sessions, so it is not affected by how much junk traffic the site gets.
And cart abandonment here is a session level rate. The industry number usually
quoted is per cart, which is higher because one user can abandon several carts.

## Value metrics

| Metric | Definition |
| --- | --- |
| Revenue | sum of `order_value` on purchase events |
| Average order value | revenue / orders |
| Revenue per session | revenue / all sessions |
| Revenue per user | revenue / all users |
| Items per order | sum of item quantity / orders |

Revenue comes from the `value` parameter on the purchase event, which is what
GA4 reports. Item level revenue, the sum of price times quantity across the
items array, is stored separately as `item_revenue_sum` and used for product
reporting. The two do not always agree, and notebook 01 measures the gap rather
than hiding it.

## User metrics

| Metric | Definition |
| --- | --- |
| Returning user | a user with more than one session in the window |
| Returning user rate | returning users / all users |
| Customer | a user with at least one order |
| Repeat customer | a user with two or more orders |
| Repeat purchase rate | repeat customers / customers |
| Repeat revenue share | revenue from orders after the first / all revenue |
| Days to first purchase | first order date minus first visit date |

New versus returning at the session level is different from this. A session is
New if it is that user's first session and Returning otherwise, so one user can
contribute both kinds.

## Attribution

Channel is first touch, taken from the source and medium on a user's first
session and stored on `dim_users`. A channel is judged on the users it
introduced, not on the session that happened to close the sale.

This is a choice, not the only right answer. First touch flatters channels at
the top of the funnel such as paid social and punishes channels that finish
journeys such as email and direct. Last touch would do the opposite. First touch
is used here because the question being asked is which channel is worth buying
more users from.

`channel_group` buckets source and medium into Direct, Organic Search, Paid,
Email, Referral, Affiliate and Other. Paid holds both search and social, so
whenever the two need to be told apart the analysis drops to `source_medium`,
where `google / cpc` and `facebook / paid_social` are separate rows. The exact
CASE expression is in `01_stg_events.sql`.

## Cohorts

Cohorts are weekly and based on a user's first visit, with weeks starting on
Monday. Week 0 is the week of the first visit and is 100% by construction.
Week index n counts users who were active in the nth week after that. The table
is stored at acquisition week by acquisition channel, so a channel level view
is a filter and the all channel view is a sum of the numerators and
denominators, never an average of the rates.

`weeks_observed` records how many weeks of history a cohort actually has. Cells
past that are missing, not zero, and both the notebook heatmap and the DAX
measure blank them out.

## Price bands

Bands are on the average price of the products viewed in a session, not on the
order value, so a session that never bought still lands in a band. Sessions with
no product view sit in a separate "No product view" bucket and are excluded from
any band comparison.

## Statistics

Rate comparisons use a two proportion z test. When more than two segments are
compared at once, p values are Holm adjusted, because otherwise one of six
segments looks significant by chance about a quarter of the time.

Confidence intervals on a rate use the Wilson method rather than the normal
approximation, since the counts at the bottom of the funnel are small enough for
the normal interval to run past 0 or 1.

Order value is compared with a percentile bootstrap and Mann Whitney rather than
a t test, because the distribution has a long right tail.

Sample sizes use `statsmodels` `NormalIndPower` at 80% power and 5%
significance, two sided, with equal arms.
