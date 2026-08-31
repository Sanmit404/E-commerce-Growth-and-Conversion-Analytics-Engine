# What the data says

Quarter covered: 1 September to 30 November 2024. 150,000 users, 228,210
sessions, 4,492 orders, $312,481 in revenue.

Every number here comes from the notebooks in `notebooks/`. Where a claim
depends on a statistical test, the test and its p value are in notebook 04.

## The baseline

| Metric | Value |
| --- | --- |
| Session conversion rate | 1.97% |
| Product view rate | 63.22% |
| View to cart | 14.55% |
| Cart to checkout | 36.61% |
| Checkout to purchase | 58.45% |
| Cart abandonment | 63.39% |
| Average order value | $69.56 |
| Revenue per session | $1.37 |
| Returning user rate | 32.66% |
| Repeat purchase rate | 8.11% |

The funnel loses sessions like this:

| Step | Sessions | Step conversion | Cumulative |
| --- | --- | --- | --- |
| Session | 228,210 | | 100% |
| Product view | 144,280 | 63.22% | 63.22% |
| Add to cart | 20,991 | 14.55% | 9.20% |
| View cart | 16,623 | 79.19% | 7.28% |
| Begin checkout | 7,685 | 46.23% | 3.37% |
| Shipping info | 6,243 | 81.24% | 2.74% |
| Payment info | 5,298 | 84.86% | 2.32% |
| Purchase | 4,492 | 84.79% | 1.97% |

## Finding 1: the payment step is broken on mobile

Mobile is 111,514 of 228,210 sessions, so this is not a small corner of the site.
Every step from the landing page down to shipping info looks similar across
devices. Then one step falls apart.

| Device | Shipping info to payment info | Median seconds on that step |
| --- | --- | --- |
| desktop | 88.87% | 90 |
| mobile | 79.37% | 160 |
| tablet | 85.68% | 89 |

The mobile gap against desktop is 9.5 percentage points, z = -10.01, Holm
adjusted p below 0.001. Tablet is 3.2 points behind desktop and does not clear
the bar after correction (p = 0.057), so mobile is the specific problem and not
just "small screens".

Two things make me confident this is the interface and not the audience.

First, mobile carries more paid social traffic than desktop, so the raw gap
could have been a traffic mix effect. A logistic regression on sessions that
already reached shipping info, controlling for channel, new versus returning and
basket price, still leaves mobile at an odds ratio of 0.48 against desktop
(p below 0.001). Channel drops out of that model almost entirely.

Second, the timing points the same way. Mobile users spend 160 seconds between
shipping info and payment info against 90 on desktop, and 304 seconds from
starting checkout to paying against 232. People who lose interest leave faster,
not slower. Sitting on a form for longer and then dropping looks like a form
that is hard to fill in on a phone.

Closing the whole gap would be worth about 195 extra orders and $13,600 a
quarter at the current AOV. That is small in absolute terms, which is honest:
only 2,496 mobile sessions reach the shipping step at all in 91 days. The real
value is that it is the one problem where the cause is clear enough to fix
without guessing.

## Finding 2: cart to checkout is the biggest leak in the middle

Only 36.61% of sessions that add an item go on to start checkout, so 63.39% of
carts are abandoned. In raw sessions the product view to add to cart step loses
more (123,289 sessions), but most of those people never showed intent. The cart
step loses people who did.

Abandonment is worst exactly where the site is paying for traffic:

| Channel | New users | Returning users |
| --- | --- | --- |
| Affiliate | 75.2% | 72.4% |
| Referral | 72.6% | 59.8% |
| Organic Search | 69.6% | 61.4% |
| Paid | 68.2% | 59.3% |
| Direct | 65.8% | 56.3% |
| Email | 62.4% | 54.3% |

Sessions that abandon and sessions that continue look almost identical on
browsing behaviour (2.38 products viewed against 2.41). Whatever separates them
is not how much they looked at, which points at something that appears at the
cart, most likely price after shipping.

## Finding 3: paid social buys users who do not buy anything

facebook / paid_social is 16.1% of acquired users and 3.97% of revenue.

| Source and medium | Users | Share of users | Revenue per user | Share of revenue |
| --- | --- | --- | --- | --- |
| google / organic | 39,111 | 26.1% | $1.95 | 24.4% |
| (direct) / (none) | 32,892 | 21.9% | $2.72 | 28.6% |
| google / cpc | 29,917 | 19.9% | $2.61 | 25.0% |
| facebook / paid_social | 24,108 | 16.1% | $0.51 | 4.0% |
| youtube.com / referral | 12,000 | 8.0% | $0.92 | 3.5% |
| newsletter / email | 7,494 | 5.0% | $4.82 | 11.6% |
| partners / affiliate | 4,478 | 3.0% | $2.07 | 3.0% |

The failure is at the top of the funnel, not at the bottom. Paid social sessions
add to cart at 6.18% against 14.55% for the site. Once they reach checkout they
convert about as well as everyone else. That is the shape you get when the ad
brings the wrong people or the landing page does not match what the ad promised,
not when checkout is broken.

Referral traffic from youtube.com has the same problem and is worse still on
session conversion at 0.85%.

## Finding 4: email is small and nobody is scaling it

Email is 5% of users and returns $4.82 per user, more than any other channel and
over twice the site average of $2.08. Email sessions convert at 4.06%, add to
cart at 22.19%, and 11.4% of email customers buy again against 8.11% overall.

There is no evidence here that email would hold that rate at ten times the
volume, and there is a selection effect, since people on a newsletter list
already liked the brand enough to sign up. It is still the clearest case in the
data for spending more attention somewhere.

## Finding 5: retention falls off a cliff after week 1

Averaged over cohorts with at least four weeks of history:

| Weeks since first visit | Users still active |
| --- | --- |
| 1 | 21.6% |
| 2 | 9.4% |
| 3 | 4.6% |
| 4 | 2.6% |
| 5 | 1.4% |
| 6 | 0.8% |

Most users end the quarter having done nothing much. 32.1% bounced without
seeing a product, 55.7% browsed and left, 7.5% abandoned a cart, and 2.7% bought
at least once.

The purchase side matches. Median gap between a first and second order is 6.5
days, and only 8.37% of orders are repeat orders. Whatever lifecycle work
happens has to land in the first week or it lands after the user is gone.

## Finding 6: expensive baskets convert worse but are worth more

| Average price viewed | View to cart | Session conversion | Revenue per session |
| --- | --- | --- | --- |
| Under $15 | 18.09% | 3.59% | $0.63 |
| $15 to $30 | 15.90% | 3.44% | $1.49 |
| $30 to $60 | 13.85% | 2.94% | $2.62 |
| $60 to $100 | 11.65% | 2.55% | $3.28 |
| $100 and up | 9.00% | 1.92% | $3.85 |

Optimising for conversion rate alone would push the site toward cheap products
and less revenue. Electronics is the clearest case: 7.25% view to cart, the
worst of any category, and $1.69 revenue per viewing session, the best.

Apparel carries the most revenue at $102,812, then Accessories at $54,457 and
Bags at $45,262. 46 of 220 products cover 80% of revenue.

## Finding 7: new users are half the traffic and a third of the value

| | Sessions | View to cart | Cart to checkout | Session conversion | Revenue per session |
| --- | --- | --- | --- | --- | --- |
| New | 150,000 | 11.81% | 32.15% | 1.16% | $0.82 |
| Returning | 78,210 | 18.80% | 40.96% | 3.52% | $2.43 |

The gap opens at the top of the funnel and widens all the way down, which is
what you would expect: people who came back already decided they liked
something. It matters here because it is a confounder. Any channel comparison
that ignores it will credit channels that happen to send more returning users.
The regression in notebook 04 holds it fixed, and mobile still comes out behind.

## Where the promo week sits

25 November to 2 December is a promotion week. It averages 5,714 sessions a day
against 2,281 outside it, 2.8% conversion against 1.8%, and $71.00 AOV against
$69.10. Any baseline that includes it is too optimistic, so the experiment
sizing in notebook 04 uses whole quarter rates and the promo week is called out
separately in notebook 01.

## What I would do next

The three things worth building are in `experiment_backlog.md`. Short version:
fix the mobile payment form first because the cause is clearest, put a shipping
cost line on the product page to attack cart abandonment, and either cut paid
social spend or rebuild its landing pages before spending more on it.

Two things I would not do yet. I would not touch checkout to purchase, which is
already 84.79% and has no obvious segment failing. And I would not chase the
low conversion rate in India and Brazil (1.05% and 1.15%) without knowing
whether the site even ships there, which is not in the data.
