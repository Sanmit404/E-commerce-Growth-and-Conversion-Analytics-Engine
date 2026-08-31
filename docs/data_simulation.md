# Why the data is simulated, and what that means

## The short version

The problem statement points at
`bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`. Querying it
needs a Google Cloud project with billing enabled, which I do not have. So the
project is built in two halves.

The BigQuery SQL in `sql/bigquery/` is the real implementation. It reads the
public table, scoped with `_TABLE_SUFFIX BETWEEN '20201101' AND '20210131'`, and
is what I would run on day one with an account. It has never been executed, and
I am not claiming otherwise.

The DuckDB SQL in `sql/duckdb/` is a line by line port of the same eight models,
and it runs locally on a generated event log that copies the GA4 export schema.
That is what produces every number in the notebooks, the dashboard and the docs.

## Why this is not just faking the answer

The risk with generated data is that you plant the finding and then discover it,
which proves nothing. Three things keep this honest.

The schema is real. `events_YYYYMMDD.parquet` has `event_params` as an array of
structs with a `value` union of `string_value`, `int_value`, `float_value` and
`double_value`, an `items` array of structs, and `device`, `geo` and
`traffic_source` records, all matching the GA4 export. The SQL that unpacks it
is the same unpacking the real table needs, so the hard part of the work is not
skipped.

The parameters are behavioural, not outcome based. I set things like "mobile
users have a harder time on the payment form" and "email users have higher
intent". I did not set "mobile converts at 1.46%". Every rate in this project is
an output of the simulation, not an input to it, and I did not know the funnel
numbers until the warehouse was built.

The analysis has to work for the numbers to be meaningful. The regression that
controls for channel, user type and basket price still finds the mobile effect,
and the chi square that finds a tiny effect size on a huge sample size is
reported as tiny. Those are the parts a hiring manager should care about, and
they behave the same on real data.

## The generating model

Each user gets a latent intent score drawn from a normal distribution, plus a
channel, a device, a country and a favourite category. Intent is the thing GA4
cannot see and it is the main reason some users buy and most do not.

Sessions come from a geometric style draw. Users with higher intent and better
channels return more often, with gaps drawn from a lognormal so most returns
happen inside a week.

Each funnel step is a Bernoulli draw on a logistic model. The log odds of a step
are a base level plus intent, plus a channel effect, plus a device effect, plus
a bonus if the session is a return visit, plus a promo bonus, plus a country
offset, plus a price penalty on expensive baskets. Every step is conditional on
the one before it, so the funnel is a real chain and not eight independent
coin flips.

The parameters are all at the top of `src/ga4_growth/simulate.py`. The main ones:

| Effect | Value | Reason |
| --- | --- | --- |
| Mobile payment step | -0.60 log odds | Card entry on a phone is the friction I wanted to be findable |
| Mobile checkout start | -0.25 | Smaller screens, more interruptions |
| Email channel add to cart | +0.70 | Email reaches people who already opted in |
| Paid social add to cart | -0.75 | Interruption traffic, low purchase intent |
| Affiliate checkout | -0.30 with atc +0.45 | Coupon traffic fills carts then leaves |
| Returning session | +0.35 to +0.45 by step | Familiarity with the site |
| Price penalty | -0.42 times log1p(price / 40) | Expensive items get more hesitation |
| Country offsets | +0.25 US down to -0.35 India | Stands in for shipping cost and payment method fit |

Two more rules on top of the logistic chain. Customers who have already bought
get a 55% chance of being pushed through from begin checkout to purchase on
later sessions, because saved cards and addresses are the usual reason repeat
buying is easier. And the payment step has a time cost drawn from a gamma
distribution with a much fatter mean on mobile, which is why mobile shows 160
seconds on that step against 90 on desktop.

Product popularity follows a Pareto draw, so a small set of SKUs takes most of
the views. That is what produces the 46 products covering 80% of revenue, and
it matches how catalogue demand normally looks.

Traffic grows about 35% across the quarter, dips on weekends, and spikes 2.5x
during 25 November to 2 December for Black Friday. Time of day has a lunch hump
and a bigger evening hump.

## What the simulator does not model

No cross device identity, so a user who browses on a phone and buys on a laptop
looks like two people. The real GA4 export has the same limitation.

No ad spend, so nothing here can compute a real ROAS or CAC. Channel comparisons
are on revenue per acquired user, which is only half the picture.

No returns, refunds or cancellations, so revenue is gross.

No search terms, no promo codes and no site content, so I cannot say anything
about on site search or merchandising.

No bot traffic. Real GA4 has some, and the data quality checks in notebook 01
would catch it if it were there.

## Swapping in the real export

The pipeline is designed so this is a small change.

1. Set up a GCP project with billing and run `bq query` against the eight files
   in `sql/bigquery/` in numeric order, materialising each as a table in your
   own dataset.
2. Export `fct_sessions`, `fct_funnel`, `fct_orders`, `fct_daily_kpis`,
   `fct_product_performance`, `dim_users` and `fct_cohort_retention` to GCS as
   parquet.
3. Point `config.RAW_DIR` at the downloaded files and skip the simulate step.
   `warehouse.register_raw_events` already reads a parquet glob.

Everything above the SQL layer stays the same, because `metrics.py` only ever
touches the fact tables and never the raw events.

The one thing that will change is the numbers. The public sample covers three
months of the Google Merchandise Store in late 2020, which is a single brand
with heavy direct traffic, so the channel mix will look nothing like this. The
funnel shape and the mobile pattern are the parts I would expect to hold up.
