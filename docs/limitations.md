# Limitations

Things that would change the conclusions, roughly in order of how much they
matter.

## The data is generated

The BigQuery models in `sql/bigquery/` are written against the real public GA4
export but have never been run, because that needs a billing account. Every
number in this repo comes from the DuckDB port running on a simulated event log.
`docs/data_simulation.md` explains how it works and what was deliberately built
into it. Treat the analysis as a demonstration of method, not as a finding about
any real store.

## Nothing here is causal

Every segment comparison is observational. Mobile users convert worse than
desktop users, but nobody was assigned a device. The logistic regression in
notebook 04 controls for channel, user type, basket price, products viewed and
session length, and the mobile effect survives at an odds ratio of 0.48 on the
checkout restricted model. That makes confounding by those five variables
unlikely. It says nothing about the variables I do not have, such as whether the
mobile audience is younger, poorer or in a different country mix by intent.

The experiment backlog exists because of this. A test is the only way to know
whether fixing the payment form moves anything.

## Statistical significance is not effect size

The chi square on device against furthest funnel step gives p = 7.9e-112, which
looks impressive and is almost meaningless on 228,210 sessions. Cramer's V is
0.035, which is a very weak association. The same caution applies to the channel
conversion tests. What decides whether a difference is worth acting on is the
size of the gap and the traffic behind it, not the p value.

## Attribution is first touch only

Channel is fixed to the source and medium of a user's first session. That
credits paid social for users it introduced and never credits it for assisting
a later conversion. Last touch or a multi touch model would rank the channels
differently, and the paid social conclusion in particular could look less bad
under a model that gives it assist credit.

I picked first touch because the question I am asking is which channel to buy
more users from. If the question were which channel to cut mid funnel, that
would be the wrong model.

## The window is too short for retention

92 days is not long enough to see a real repeat purchase cycle. Median time
between a first and second order is 6.5 days here, which is fast for retail and
is an artefact of the window. Cohorts acquired in November have only two or
three weeks of history, which is why `weeks_observed` exists and why the
retention heatmap blanks out cells past it. Any lifetime value estimate from
this data would be wrong.

## Promo week distorts everything

25 November to 2 December runs at 5,714 sessions a day against 2,281 the rest of
the time, and 2.8% conversion against 1.8%. Eight of 91 days carry a
disproportionate share of the revenue. Every headline number in this repo
includes promo week. Notebook 01 reports the split so the effect is visible, but
if these numbers were being used to set a target, promo week should come out
first.

## Session grain hides multi visit journeys

The funnel is measured per session, so a user who researches on Monday and buys
on Thursday shows one abandoned session and one converted session. That is the
right grain for asking where a checkout flow breaks and the wrong grain for
asking how long people take to decide. Days to first purchase in notebook 03 is
the only user grain view of that, and it is coarse.

## No cross device identity

`user_pseudo_id` is per browser. A phone to laptop journey looks like two users.
This makes mobile look worse than it is, because some of the mobile sessions
that "abandon" ended in a desktop purchase that got credited elsewhere. The real
GA4 export has the same problem, and it is one reason I would not act on the
mobile finding without testing it.

## Two revenue numbers that do not match

Order revenue is the `value` parameter on the purchase event. Item revenue is
the sum of price times quantity across the items array. They differ, and the gap
is measured in notebook 01 rather than reconciled away. Anything at order or
session level uses order revenue. Anything at product level has to use item
revenue, because there is no other way to split an order across SKUs. So the
category revenue in notebook 03 will not sum exactly to total revenue.

## Country findings have no context

India converts at 1.05% and Brazil at 1.15% against 2.56% for the United States.
There is no shipping cost, delivery time, currency, payment method or catalogue
availability data in a GA4 export, and all of those are more likely explanations
than anything about the site. I have not proposed any action on this.

## Sample sizes assume clean traffic

The experiment sizing uses observed daily volume at each funnel step and assumes
a clean 50/50 split with no assignment leak, no novelty effect and no seasonal
break. In practice a test that needs 40 days will overlap something, and the
usable numbers are the ones that fit in two or three weeks.

## Single analyst, no review

The metric definitions, the SQL and the interpretation are all mine. Nothing has
been checked against a second source, because there is no second source. On a
real team the first thing I would want is someone to argue with about whether
the funnel should be session grain.
