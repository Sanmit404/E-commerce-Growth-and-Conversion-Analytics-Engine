# Experiment backlog

Five experiments, ordered by how confident I am that the problem is real and
that a product change can move it.

All sizing is for a two sided test at 80% power and 5% significance, using the
traffic each step actually gets in this data. Days are calendar days with a
50/50 split. Anything longer than about six weeks is flagged, because a test
that runs that long usually gets contaminated by a promo, a site change or
seasonality before it finishes.

Sizing numbers come from `stats.sample_size_per_arm` and the tables in notebook
04.

## 1. Rebuild the mobile payment form

Mobile drops 9.5 percentage points more than desktop between shipping info and
payment info, and spends 160 seconds on that step against 90 on desktop. The gap
survives Holm correction and survives a logistic regression that controls for
channel, new versus returning and basket price.

Hypothesis: mobile users abandon at the payment step because entering card
details on a phone form is slow. Making the form shorter and adding a wallet
option should raise the share of mobile users who complete it.

What to build: single column layout, numeric keyboard for the card fields,
autofill and card scan enabled, and Apple Pay and Google Pay above the card
form.

Primary metric: mobile shipping info to payment info rate, baseline 79.37%.
Secondary: mobile session conversion rate, median time on the payment step.
Guardrails: payment failure rate, refund rate, desktop conversion rate.

| Relative lift to detect | Sample per arm | Days |
| --- | --- | --- |
| 3% | 4,333 | 321 |
| 5% | 1,509 | 112 |
| 8% | 557 | 42 |
| 10% | 342 | 26 |

Only 27 mobile sessions a day reach the shipping step, which is the honest
problem with this test. I would run it targeting a 10% relative lift, which is
plausible for adding wallets, and accept that anything smaller is not
measurable at this traffic level. If it needs to be more sensitive, run it on
mobile checkout to purchase instead, which has more sessions in the denominator
but mixes in steps the change does not touch.

## 2. Show delivery cost and time on the product page

63.39% of carts never reach checkout. Sessions that abandon and sessions that
continue view almost the same number of products (2.38 against 2.41), so the
split is not about how much browsing happened. Abandonment is worst for new
users from affiliate, referral and paid channels, which are the ones least
likely to already know the shipping policy.

Hypothesis: people add an item, see the delivery cost for the first time at the
cart, and leave. Showing it earlier means fewer carts and fewer surprises, but
more of the carts that do get created should go through.

What to build: a delivery cost and estimated arrival line on the product page,
under the price, using the visitor's country.

Primary metric: cart to checkout rate, baseline 36.61%.
Secondary: session conversion rate, revenue per session.
Guardrails: add to cart rate, which this change is expected to lower slightly.

| Relative lift to detect | Sample per arm | Days |
| --- | --- | --- |
| 5% | 10,982 | 96 |
| 8% | 4,314 | 38 |
| 10% | 2,771 | 24 |

Sizing is on cart sessions, of which there are 231 a day. A four week run can
pick up an 8% lift, which is a reasonable target.

Worth saying clearly: revenue per session, not cart to checkout, is what
actually decides this one. If add to cart falls more than cart to checkout
rises, the change is a loss even though the headline metric went up.

## 3. Match paid social landing pages to the ad

facebook / paid_social is 16.1% of acquired users and 4.0% of revenue. Those
sessions add to cart at 6.18% against 14.55% site wide, but once they reach
checkout they convert normally. The problem is at the top of the funnel.

Hypothesis: paid social lands on a generic home or category page that has
nothing to do with the ad, so people bounce before seeing a relevant product.
Sending each ad to a page showing that product should improve the top of the
funnel.

What to build: a landing page per ad creative, showing the product from the ad
plus three related items, with the ad's offer repeated at the top.

Primary metric: paid social view to cart rate, baseline 6.18%.
Secondary: paid social session conversion rate (0.53%), revenue per acquired
user.
Guardrails: cost per acquisition, bounce rate.

Paid social gets 357 sessions a day, of which 168 view a product.

| Metric | Relative lift | Sample per arm | Days |
| --- | --- | --- | --- |
| view to cart | 15% | 11,308 | 135 |
| view to cart | 20% | 6,493 | 78 |
| session conversion | 20% | 80,414 | 451 |
| session conversion | 30% | 37,272 | 209 |

None of that fits in a usable window, and that is the finding. At 0.53%
conversion and 357 sessions a day, paid social cannot be A/B tested to a
conclusion before the quarter ends. So this is not an experiment, it is a
budget decision.

What I would actually do: cut paid social spend by half for four weeks and
watch total revenue and revenue per acquired user across all channels. If total
revenue does not fall, the channel was not paying for itself and the money moves
to email and paid search. That is a before and after read rather than a clean
test, and it is worth being explicit that it cannot separate the channel effect
from seasonality. It is still a better use of four weeks than an underpowered
landing page test.

## 4. Trust and returns block on the product page

The product view to add to cart step loses 123,289 sessions, more than any other
step. The loss is concentrated at higher prices: 18.09% view to cart under $15
against 9.00% above $100. Electronics has the worst view to cart of any category
at 7.25% and the best revenue per viewing session at $1.69.

Hypothesis: on expensive items people hesitate because they cannot judge whether
returning something will be painful. Putting the returns policy, warranty and
review count next to the add to cart button should reduce that hesitation.

What to build: a compact block under the add to cart button with the returns
window, warranty length and review count. Shown only on items over $60.

Primary metric: view to cart rate on sessions whose average viewed price is over
$60, baseline 11.65% across the two bands above $60.
Secondary: revenue per session, AOV.
Guardrails: return rate, since making returns more visible can raise it.

| Relative lift to detect | Sample per arm | Days |
| --- | --- | --- |
| 3% | 103,700 | 131 |
| 5% | 37,633 | 48 |
| 8% | 14,874 | 19 |

Those numbers are for all product view sessions. Only 18,108 sessions in the
quarter have an average viewed price above $60, which is 199 a day or about 100
per arm, and that pushes even an 8% test past a year. So this one should run
site wide on all price points and accept a diluted effect, with the price band
split reported as a secondary read rather than the thing the test is powered
for.

## 5. Welcome series in the first week

Retention drops from 21.6% in week 1 to 9.4% in week 2 and 0.8% by week 6.
Median time from a first order to a second is 6.5 days. Email users are 5% of
the base and return $4.82 each against a $2.08 site average.

Hypothesis: most users are gone before any lifecycle marketing reaches them.
A short welcome series sent inside the first week should keep more of them
active and bring some back to buy.

What to build: three emails over seven days after signup. First a welcome with
the categories the user browsed, then social proof on those categories, then a
reminder of anything left in the cart.

Primary metric: week 1 retention for the treated cohort, baseline 21.6%.
Secondary: user conversion rate within 14 days, revenue per acquired user.
Guardrails: unsubscribe rate, spam complaint rate.

Sizing here is on users who give an email address, and this dataset does not
record which users did. So I cannot size it honestly from what I have, and I
have not made a number up. What the data does support is that email users behave
better than everyone else and that the window to reach a user is about a week.
The first step is instrumenting signups, not running a test.

## What I would not test

Checkout to purchase is 84.79% overall and no segment fails on it after the
payment step, so there is nothing obvious to fix.

Country level conversion looks bad for India at 1.05% and Brazil at 1.15%
against 2.56% for the United States, but the data has no shipping or pricing
information for those markets. Testing a site change there would be guessing at
a cause.
