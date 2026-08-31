"""
Builds a GA4-shaped raw event export so the whole pipeline runs without a
BigQuery billing account.

The output parquet files copy the schema of
`bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`: nested
event_params, nested items, and one file per day instead of one BigQuery shard
per day. Every SQL model in sql/duckdb/ is a direct port of the BigQuery model
that reads the real export, so the same UNNEST logic is exercised either way.

Behaviour rules and their sources are documented in docs/data_simulation.md.
Nothing here is tuned to a specific answer: the parameters are channel, device
and lifecycle effects, and the funnel numbers fall out of them.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from . import config

N_USERS = 150_000
MAX_SESSIONS = 12
MAX_VIEWED_ITEMS = 4

# source, medium, campaign, share of new users, and how much better or worse
# that channel behaves at each funnel step (log-odds).
CHANNELS = [
    ("google", "organic", "(organic)", 0.26, {"view": 0.15, "atc": 0.10, "checkout": 0.05, "purchase": 0.05}),
    ("(direct)", "(none)", "(direct)", 0.22, {"view": 0.30, "atc": 0.35, "checkout": 0.25, "purchase": 0.20}),
    ("google", "cpc", "brand_search", 0.09, {"view": 0.35, "atc": 0.40, "checkout": 0.30, "purchase": 0.20}),
    ("google", "cpc", "shopping_feed", 0.11, {"view": 0.20, "atc": 0.25, "checkout": 0.10, "purchase": 0.05}),
    ("facebook", "paid_social", "prospecting_broad", 0.16, {"view": -0.55, "atc": -0.75, "checkout": -0.35, "purchase": -0.20}),
    ("youtube.com", "referral", "(referral)", 0.08, {"view": -0.30, "atc": -0.45, "checkout": -0.20, "purchase": -0.10}),
    ("newsletter", "email", "weekly_drop", 0.05, {"view": 0.55, "atc": 0.70, "checkout": 0.45, "purchase": 0.35}),
    ("partners", "affiliate", "coupon_partners", 0.03, {"view": 0.10, "atc": 0.45, "checkout": -0.30, "purchase": -0.45}),
]

DEVICES = [
    ("desktop", 0.44, {"view": 0.10, "atc": 0.05, "checkout": 0.15, "shipping": 0.10, "payment": 0.15, "purchase": 0.10}),
    ("mobile", 0.49, {"view": -0.05, "atc": -0.10, "checkout": -0.25, "shipping": -0.15, "payment": -0.60, "purchase": -0.20}),
    ("tablet", 0.07, {"view": 0.00, "atc": -0.05, "checkout": -0.10, "shipping": -0.05, "payment": -0.20, "purchase": -0.05}),
]

DESKTOP_OS = [("Macintosh", 0.45), ("Windows", 0.48), ("Linux", 0.07)]
MOBILE_OS = [("Android", 0.55), ("iOS", 0.45)]
BROWSERS = [("Chrome", 0.62), ("Safari", 0.24), ("Edge", 0.08), ("Firefox", 0.06)]

# country, share of users, quality offset, region, city
GEOS = [
    ("United States", 0.38, 0.25, "California", "Mountain View"),
    ("India", 0.14, -0.35, "Karnataka", "Bengaluru"),
    ("United Kingdom", 0.08, 0.10, "England", "London"),
    ("Canada", 0.07, 0.15, "Ontario", "Toronto"),
    ("Germany", 0.06, 0.05, "Berlin", "Berlin"),
    ("Japan", 0.05, 0.00, "Tokyo", "Tokyo"),
    ("Brazil", 0.05, -0.30, "Sao Paulo", "Sao Paulo"),
    ("Australia", 0.04, 0.05, "New South Wales", "Sydney"),
    ("France", 0.04, 0.00, "Ile-de-France", "Paris"),
    ("Netherlands", 0.03, 0.05, "North Holland", "Amsterdam"),
    ("Singapore", 0.03, 0.00, "Singapore", "Singapore"),
    ("Mexico", 0.03, -0.25, "Mexico City", "Mexico City"),
]

# category, share of product views, price range, extra pull on add to cart
CATEGORIES = [
    ("Apparel", 0.26, (16, 75), 0.10),
    ("Drinkware", 0.15, (8, 30), 0.35),
    ("Bags", 0.11, (25, 140), -0.10),
    ("Office", 0.14, (2, 40), 0.30),
    ("Accessories", 0.12, (4, 45), 0.20),
    ("Electronics", 0.08, (25, 210), -0.35),
    ("Lifestyle", 0.07, (10, 90), 0.00),
    ("Headgear", 0.04, (12, 35), 0.15),
    ("Stationery", 0.03, (2, 18), 0.25),
]

PRODUCT_WORDS = {
    "Apparel": ["Zip Hoodie", "Crewneck Sweatshirt", "Tee", "Cap Sleeve Tee", "Long Sleeve Tee", "Track Jacket"],
    "Drinkware": ["Bottle Infuser", "Ceramic Mug", "Insulated Tumbler", "Travel Mug", "Water Bottle"],
    "Bags": ["Backpack", "Tote Bag", "Sling Bag", "Laptop Sleeve", "Duffel Bag"],
    "Office": ["Notebook", "Sticky Notes", "Desk Pad", "Pen Set", "Mouse Pad"],
    "Accessories": ["Keychain", "Socks", "Enamel Pin", "Lanyard", "Sunglasses"],
    "Electronics": ["Wireless Charger", "Bluetooth Speaker", "USB-C Hub", "Earbuds Case", "Power Bank"],
    "Lifestyle": ["Yoga Mat", "Blanket", "Picnic Set", "Plant Pot", "Candle"],
    "Headgear": ["Cap", "Beanie", "Bucket Hat", "Visor"],
    "Stationery": ["Pencil Pack", "Highlighter Set", "Journal", "Sticker Sheet"],
}

COLOURS = ["Black", "Charcoal", "Navy", "White", "Olive", "Sand", "Red", "Sky Blue"]

# Base log-odds of each funnel step given the previous one. Tuned so the
# aggregate rates land in the range the real GA4 sample store shows
# (see docs/data_simulation.md).
BASE_LOGITS = {
    "view": 0.25,
    "atc": -2.42,
    "cart": 1.20,
    "checkout": -0.92,
    "shipping": 1.10,
    "payment": 1.35,
    "purchase": 1.25,
}


def _pick(rng, options, size, weight_index=1):
    weights = np.array([o[weight_index] for o in options], dtype=float)
    weights = weights / weights.sum()
    return rng.choice(len(options), size=size, p=weights)


def _arr(values, type=None) -> pa.Array:
    """pa.array can hand back a ChunkedArray, which StructArray refuses."""
    out = pa.array(values, type=type)
    if isinstance(out, pa.ChunkedArray):
        out = out.combine_chunks()
    return out


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def build_catalog(rng: np.random.Generator) -> pd.DataFrame:
    rows = []
    for cat_i, (category, _, (lo, hi), atc_lift) in enumerate(CATEGORIES):
        for word in PRODUCT_WORDS[category]:
            for colour in COLOURS[:5]:
                price = float(np.round(rng.uniform(lo, hi), 2))
                rows.append(
                    {
                        "item_id": f"GGOE{cat_i}{len(rows):05d}",
                        "item_name": f"Google {colour} {word}",
                        "item_category": category,
                        "price": price,
                        "category_index": cat_i,
                        "atc_lift": atc_lift,
                    }
                )
    catalog = pd.DataFrame(rows)
    # Popularity is heavily skewed, a handful of SKUs carry most of the views.
    pop = rng.pareto(1.3, len(catalog)) + 0.15
    cat_share = np.array([CATEGORIES[i][1] for i in catalog["category_index"]])
    weight = pop * cat_share
    catalog["view_weight"] = weight / weight.sum()
    return catalog


def build_users(rng: np.random.Generator, n_users: int) -> pd.DataFrame:
    dates = pd.date_range(config.START_DATE, config.END_DATE, freq="D")
    n_days = len(dates)

    # New users grow slowly through the quarter and spike in Black Friday week.
    trend = np.linspace(1.0, 1.35, n_days)
    weekday = np.where(pd.Series(dates).dt.dayofweek.isin([5, 6]), 0.85, 1.0)
    bf_week = ((dates >= "2024-11-25") & (dates <= "2024-12-02")).astype(float) * 1.5 + 1.0
    acq_weight = trend * weekday * bf_week
    acq_weight = acq_weight / acq_weight.sum()

    first_day = rng.choice(n_days, size=n_users, p=acq_weight)
    channel = _pick(rng, CHANNELS, n_users, weight_index=3)
    device = _pick(rng, DEVICES, n_users, weight_index=1)
    geo = _pick(rng, GEOS, n_users, weight_index=1)

    os = np.empty(n_users, dtype=object)
    desktop_mask = np.isin(device, [0, 2])
    n_desktop = int(desktop_mask.sum())
    os[desktop_mask] = np.array([o[0] for o in DESKTOP_OS])[_pick(rng, DESKTOP_OS, n_desktop)]
    os[~desktop_mask] = np.array([o[0] for o in MOBILE_OS])[_pick(rng, MOBILE_OS, n_users - n_desktop)]

    browser = np.array([b[0] for b in BROWSERS])[_pick(rng, BROWSERS, n_users)]

    users = pd.DataFrame(
        {
            "user_index": np.arange(n_users),
            "user_pseudo_id": [f"{rng.integers(1_000_000, 9_999_999)}.{rng.integers(1_000_000_000, 9_999_999_999)}" for _ in range(n_users)],
            "first_day": first_day,
            "channel": channel,
            "device": device,
            "geo": geo,
            "operating_system": os,
            "browser": browser,
            # Latent shopping intent. Not observable in GA4, it is what makes
            # some users convert and others bounce.
            "intent": rng.normal(0, 0.85, n_users),
            "favourite_category": _pick(rng, CATEGORIES, n_users, weight_index=1),
        }
    )
    users["device_name"] = [DEVICES[i][0] for i in users["device"]]
    users["country"] = [GEOS[i][0] for i in users["geo"]]
    users["region"] = [GEOS[i][3] for i in users["geo"]]
    users["city"] = [GEOS[i][4] for i in users["geo"]]
    users["source"] = [CHANNELS[i][0] for i in users["channel"]]
    users["medium"] = [CHANNELS[i][1] for i in users["channel"]]
    users["campaign"] = [CHANNELS[i][2] for i in users["channel"]]
    return users


def build_sessions(rng: np.random.Generator, users: pd.DataFrame) -> pd.DataFrame:
    n_users = len(users)
    n_days = (pd.Timestamp(config.END_DATE) - pd.Timestamp(config.START_DATE)).days + 1

    # Return propensity: better channels and higher intent come back more often.
    channel_quality = np.array([CHANNELS[i][4]["atc"] for i in users["channel"]])
    return_logit = -0.55 + 0.45 * users["intent"].to_numpy() + 0.5 * channel_quality
    p_return = sigmoid(return_logit)

    # Number of sessions per user from a geometric-style draw on p_return.
    draws = rng.random((n_users, MAX_SESSIONS - 1))
    keeps = draws < p_return[:, None]
    n_sessions = 1 + (np.cumprod(keeps, axis=1)).sum(axis=1)

    user_index = np.repeat(users["user_index"].to_numpy(), n_sessions)
    session_number = np.concatenate([np.arange(1, k + 1) for k in n_sessions])

    # Gaps between sessions, right skewed: most returns happen within a week.
    gaps = np.ceil(rng.lognormal(1.35, 0.95, len(user_index))).astype(int)
    gaps[session_number == 1] = 0
    day_offset = pd.Series(gaps).groupby(user_index).cumsum().to_numpy()
    session_day = users["first_day"].to_numpy()[user_index] + day_offset

    sessions = pd.DataFrame(
        {
            "user_index": user_index,
            "session_number": session_number,
            "day": session_day,
        }
    )
    sessions = sessions[sessions["day"] < n_days].reset_index(drop=True)

    hour = rng.choice(24, size=len(sessions), p=_hour_profile())
    minute = rng.integers(0, 60, len(sessions))
    second = rng.integers(0, 60, len(sessions))
    start = (
        pd.Timestamp(config.START_DATE)
        + pd.to_timedelta(sessions["day"], unit="D")
        + pd.to_timedelta(hour, unit="h")
        + pd.to_timedelta(minute, unit="m")
        + pd.to_timedelta(second, unit="s")
    )
    sessions["hour"] = hour
    sessions["session_start"] = start
    # pandas stores datetimes in microseconds, so be explicit about the unit
    # instead of relying on astype('int64').
    start_seconds = start.to_numpy().astype("datetime64[s]").astype("int64")
    sessions["ga_session_id"] = start_seconds + sessions["user_index"].to_numpy() % 997
    sessions = sessions.sort_values(["session_start"]).reset_index(drop=True)
    return sessions


def _hour_profile():
    # Two humps: lunch break and evening browsing.
    hours = np.arange(24)
    profile = (
        0.6
        + 1.1 * np.exp(-0.5 * ((hours - 13) / 3.0) ** 2)
        + 1.4 * np.exp(-0.5 * ((hours - 21) / 2.6) ** 2)
        + 0.15 * np.exp(-0.5 * ((hours - 3) / 2.0) ** 2)
    )
    return profile / profile.sum()


def score_funnel(rng: np.random.Generator, sessions: pd.DataFrame, users: pd.DataFrame, catalog: pd.DataFrame) -> pd.DataFrame:
    n = len(sessions)
    u = sessions["user_index"].to_numpy()

    intent = users["intent"].to_numpy()[u]
    channel = users["channel"].to_numpy()[u]
    device = users["device"].to_numpy()[u]
    geo_bonus = np.array([GEOS[i][2] for i in users["geo"].to_numpy()[u]])

    chan_eff = {k: np.array([CHANNELS[i][4][k] for i in channel]) for k in ["view", "atc", "checkout", "purchase"]}
    dev_eff = {k: np.array([DEVICES[i][2][k] for i in device]) for k in ["view", "atc", "checkout", "shipping", "payment", "purchase"]}

    returning = (sessions["session_number"].to_numpy() > 1).astype(float)
    date = pd.Timestamp(config.START_DATE) + pd.to_timedelta(sessions["day"].to_numpy(), unit="D")
    promo = ((date >= "2024-11-25") & (date <= "2024-12-02")).astype(float)
    late_night = np.isin(sessions["hour"].to_numpy(), [0, 1, 2, 3, 4, 5]).astype(float)

    # Items looked at in this session, drawn from the catalogue.
    n_view = rng.integers(1, MAX_VIEWED_ITEMS + 1, n)
    item_matrix = rng.choice(len(catalog), size=(n, MAX_VIEWED_ITEMS), p=catalog["view_weight"].to_numpy())
    prices = catalog["price"].to_numpy()[item_matrix]
    atc_lift = catalog["atc_lift"].to_numpy()[item_matrix]
    view_mask = np.arange(MAX_VIEWED_ITEMS)[None, :] < n_view[:, None]
    basket_price = np.where(view_mask, prices, np.nan)
    mean_price = np.nanmean(basket_price, axis=1)
    mean_atc_lift = np.nanmean(np.where(view_mask, atc_lift, np.nan), axis=1)

    # Expensive baskets need more convincing.
    price_penalty = -0.42 * np.log1p(mean_price / 40.0)

    logit_view = BASE_LOGITS["view"] + 0.55 * intent + chan_eff["view"] + dev_eff["view"] + 0.45 * returning + 0.2 * promo + geo_bonus * 0.4 - 0.25 * late_night
    viewed = rng.random(n) < sigmoid(logit_view)

    logit_atc = (
        BASE_LOGITS["atc"] + 0.70 * intent + chan_eff["atc"] + dev_eff["atc"] + 0.40 * returning
        + 0.45 * promo + mean_atc_lift + price_penalty + geo_bonus
    )
    added = viewed & (rng.random(n) < sigmoid(logit_atc))

    viewed_cart = added & (rng.random(n) < sigmoid(BASE_LOGITS["cart"] + 0.2 * intent))

    logit_checkout = BASE_LOGITS["checkout"] + 0.5 * intent + chan_eff["checkout"] + dev_eff["checkout"] + 0.35 * returning + 0.3 * promo + geo_bonus
    began_checkout = viewed_cart & (rng.random(n) < sigmoid(logit_checkout))

    logit_ship = BASE_LOGITS["shipping"] + 0.3 * intent + dev_eff["shipping"] + 0.25 * returning
    added_shipping = began_checkout & (rng.random(n) < sigmoid(logit_ship))

    logit_pay = BASE_LOGITS["payment"] + 0.3 * intent + dev_eff["payment"] + 0.30 * returning + geo_bonus
    added_payment = added_shipping & (rng.random(n) < sigmoid(logit_pay))

    logit_purchase = BASE_LOGITS["purchase"] + 0.35 * intent + chan_eff["purchase"] + dev_eff["purchase"] + 0.25 * returning + price_penalty * 0.5
    purchased = added_payment & (rng.random(n) < sigmoid(logit_purchase))

    sessions = sessions.copy()
    sessions["viewed_product"] = viewed
    sessions["added_to_cart"] = added
    sessions["viewed_cart"] = viewed_cart
    sessions["began_checkout"] = began_checkout
    sessions["added_shipping"] = added_shipping
    sessions["added_payment"] = added_payment
    sessions["purchased"] = purchased
    sessions["n_view_items"] = np.where(viewed, n_view, 0)
    sessions["n_cart_items"] = np.where(added, np.minimum(n_view, rng.integers(1, 4, n)), 0)
    sessions["removed_from_cart"] = added & (rng.random(n) < 0.11)
    sessions["n_pageviews"] = 1 + rng.poisson(1.4 + 2.2 * viewed + 1.6 * began_checkout)
    # How fast the session moves. Mobile checkout takes longer because the
    # payment form is harder to fill on a small screen, which is the same effect
    # that shows up as the payment step drop off.
    sessions["speed"] = rng.lognormal(0, 0.45, n)
    is_mobile = device == 1
    sessions["payment_friction_sec"] = np.where(
        is_mobile, rng.gamma(4.0, 22.0, n), rng.gamma(2.0, 9.0, n)
    ).round()
    sessions["_item_matrix"] = list(item_matrix)
    return sessions


def _loyalty_pass(sessions: pd.DataFrame) -> pd.DataFrame:
    """Customers who already bought convert more easily on later sessions.

    Saved payment and address details are the usual reason, so the lift is
    applied from begin_checkout onwards rather than at the top of the funnel.
    """
    sessions = sessions.sort_values(["user_index", "session_number"]).reset_index(drop=True)
    bought_before = sessions.groupby("user_index")["purchased"].cumsum() - sessions["purchased"].astype(int)
    rng = np.random.default_rng(config.RANDOM_SEED + 7)

    candidates = (bought_before > 0) & sessions["began_checkout"] & ~sessions["purchased"]
    upgrade = candidates & (rng.random(len(sessions)) < 0.55)
    for flag in ["added_shipping", "added_payment", "purchased"]:
        sessions.loc[upgrade, flag] = True
    return sessions.sort_values("session_start").reset_index(drop=True)


def build_events(rng: np.random.Generator, sessions: pd.DataFrame, users: pd.DataFrame, catalog: pd.DataFrame) -> pd.DataFrame:
    """Explode session level flags into one row per GA4 event."""
    frames = []
    item_matrix = np.vstack(sessions["_item_matrix"].to_numpy())
    s_idx = np.arange(len(sessions))
    speed = sessions["speed"].to_numpy()
    friction = sessions["payment_friction_sec"].to_numpy()

    def add(name, rows, offset, item_slots=None, order=0):
        if len(rows) == 0:
            return
        frames.append(
            pd.DataFrame(
                {
                    "session_row": rows,
                    "event_name": name,
                    "offset": offset,
                    "slot_start": -1 if item_slots is None else item_slots[0],
                    "slot_end": -1 if item_slots is None else item_slots[1],
                    "order": order,
                }
            )
        )

    add("session_start", s_idx, np.zeros(len(sessions)), order=0)

    first = s_idx[sessions["session_number"].to_numpy() == 1]
    add("first_visit", first, np.ones(len(first)), order=1)

    # page_view: one per page, spread over the session
    pv_counts = sessions["n_pageviews"].to_numpy()
    pv_rows = np.repeat(s_idx, pv_counts)
    pv_seq = np.concatenate([np.arange(c) for c in pv_counts])
    add("page_view", pv_rows, 2 + pv_seq * 25 + rng.integers(0, 12, len(pv_rows)), order=2)

    viewers = s_idx[sessions["viewed_product"].to_numpy()]
    add("view_item_list", viewers, 8 + rng.integers(0, 10, len(viewers)), order=3)

    # view_item, one event per product looked at
    vi_counts = sessions["n_view_items"].to_numpy()
    vi_rows = np.repeat(s_idx, vi_counts)
    vi_seq = np.concatenate([np.arange(c) for c in vi_counts]) if vi_counts.sum() else np.array([], dtype=int)
    add("select_item", vi_rows, 20 * speed[vi_rows] + vi_seq * 40, item_slots=(vi_seq, vi_seq + 1), order=4)
    add("view_item", vi_rows, 25 * speed[vi_rows] + vi_seq * 40, item_slots=(vi_seq, vi_seq + 1), order=5)

    # add_to_cart, one event per item added
    atc_counts = sessions["n_cart_items"].to_numpy()
    atc_rows = np.repeat(s_idx, atc_counts)
    atc_seq = np.concatenate([np.arange(c) for c in atc_counts]) if atc_counts.sum() else np.array([], dtype=int)
    add("add_to_cart", atc_rows, 200 * speed[atc_rows] + atc_seq * 30, item_slots=(atc_seq, atc_seq + 1), order=6)

    removed = s_idx[sessions["removed_from_cart"].to_numpy()]
    add("remove_from_cart", removed, 260 + rng.integers(0, 40, len(removed)), item_slots=(np.zeros(len(removed), int), np.ones(len(removed), int)), order=7)

    cart_slots = (np.zeros(len(sessions), int), atc_counts)
    for name, base, order, flag, extra in [
        ("view_cart", 300, 8, "viewed_cart", 0.0),
        ("begin_checkout", 360, 9, "began_checkout", 0.0),
        ("add_shipping_info", 430, 10, "added_shipping", 0.0),
        ("add_payment_info", 500, 11, "added_payment", 1.0),
        ("purchase", 570, 12, "purchased", 1.0),
    ]:
        rows = s_idx[sessions[flag].to_numpy()]
        offset = base * speed[rows] + extra * friction[rows] + rng.integers(0, 45, len(rows))
        add(name, rows, offset, item_slots=(cart_slots[0][rows], cart_slots[1][rows]), order=order)

    events = pd.concat(frames, ignore_index=True)
    session_us = sessions["session_start"].to_numpy().astype("datetime64[us]").astype("int64")
    events["event_timestamp"] = (
        session_us[events["session_row"]]
        + (events["offset"].to_numpy() * 1_000_000).astype("int64")
    )
    events = events.sort_values(["event_timestamp", "session_row", "order"]).reset_index(drop=True)
    events["item_matrix_row"] = events["session_row"]
    events.attrs["item_matrix"] = item_matrix
    return events


def _items_arrays(events: pd.DataFrame, item_matrix: np.ndarray, catalog: pd.DataFrame, rng: np.random.Generator):
    """Flat item arrays plus list offsets, in event order."""
    slot_start = events["slot_start"].to_numpy()
    slot_end = events["slot_end"].to_numpy()
    counts = np.where(slot_start < 0, 0, np.maximum(slot_end - slot_start, 0))
    offsets = np.zeros(len(events) + 1, dtype=np.int32)
    np.cumsum(counts, out=offsets[1:])

    rows = np.repeat(events["item_matrix_row"].to_numpy(), counts)
    starts = np.repeat(slot_start, counts)
    within = np.arange(counts.sum()) - np.repeat(offsets[:-1], counts)
    cols = starts + within
    catalog_rows = item_matrix[rows, cols]

    quantity = np.where(rng.random(len(catalog_rows)) < 0.18, 2, 1).astype("int64")
    struct = pa.StructArray.from_arrays(
        [
            _arr(catalog["item_id"].to_numpy()[catalog_rows]),
            _arr(catalog["item_name"].to_numpy()[catalog_rows]),
            _arr(catalog["item_category"].to_numpy()[catalog_rows]),
            _arr(catalog["price"].to_numpy()[catalog_rows], type=pa.float64()),
            _arr(quantity, type=pa.int64()),
        ],
        names=["item_id", "item_name", "item_category", "price", "quantity"],
    )
    items = pa.ListArray.from_arrays(_arr(offsets, type=pa.int32()), struct)

    revenue = np.zeros(len(events))
    qty_total = np.zeros(len(events), dtype="int64")
    line_value = catalog["price"].to_numpy()[catalog_rows] * quantity
    event_of_item = np.repeat(np.arange(len(events)), counts)
    np.add.at(revenue, event_of_item, line_value)
    np.add.at(qty_total, event_of_item, quantity)
    return items, np.round(revenue, 2), qty_total


def _params_array(events: pd.DataFrame, sessions: pd.DataFrame) -> pa.Array:
    """Five event_params per event, laid out exactly like the GA4 export."""
    n = len(events)
    session_row = events["session_row"].to_numpy()
    ga_session_id = sessions["ga_session_id"].to_numpy()[session_row]
    ga_session_number = sessions["session_number"].to_numpy()[session_row]
    engagement = np.clip((events["offset"].to_numpy() * 1000).astype("int64"), 0, None)

    page = np.where(
        events["event_name"].to_numpy() == "purchase",
        "/ordercompleted.html",
        np.where(np.isin(events["event_name"].to_numpy(), ["begin_checkout", "add_shipping_info", "add_payment_info"]), "/checkout.html",
                 np.where(events["event_name"].to_numpy() == "view_item", "/product.html", "/home.html")),
    )

    keys = np.tile(np.array(["ga_session_id", "ga_session_number", "engagement_time_msec", "page_location", "page_title"]), n)
    string_value = np.empty(n * 5, dtype=object)
    int_value = np.full(n * 5, None, dtype=object)

    int_value[0::5] = ga_session_id
    int_value[1::5] = ga_session_number
    int_value[2::5] = engagement
    string_value[3::5] = np.char.add("https://shop.googlemerchandisestore.com", page.astype(str))
    string_value[4::5] = page

    value = pa.StructArray.from_arrays(
        [
            _arr(string_value, type=pa.string()),
            _arr(int_value, type=pa.int64()),
            _arr(np.full(n * 5, None, dtype=object), type=pa.float64()),
        ],
        names=["string_value", "int_value", "double_value"],
    )
    struct = pa.StructArray.from_arrays([_arr(keys), value], names=["key", "value"])
    offsets = _arr(np.arange(0, n * 5 + 1, 5, dtype=np.int32), type=pa.int32())
    return pa.ListArray.from_arrays(offsets, struct)


def to_arrow(events: pd.DataFrame, sessions: pd.DataFrame, users: pd.DataFrame, catalog: pd.DataFrame, rng) -> pa.Table:
    session_row = events["session_row"].to_numpy()
    user_row = sessions["user_index"].to_numpy()[session_row]
    ts = events["event_timestamp"].to_numpy()
    event_date = pd.to_datetime(ts, unit="us").strftime("%Y%m%d")

    items, revenue, qty = _items_arrays(events, events.attrs["item_matrix"], catalog, rng)
    is_purchase = events["event_name"].to_numpy() == "purchase"

    device = pa.StructArray.from_arrays(
        [
            _arr(users["device_name"].to_numpy()[user_row]),
            _arr(users["operating_system"].to_numpy()[user_row].astype(str)),
            pa.StructArray.from_arrays([_arr(users["browser"].to_numpy()[user_row].astype(str))], names=["browser"]),
        ],
        names=["category", "operating_system", "web_info"],
    )
    geo = pa.StructArray.from_arrays(
        [
            _arr(users["country"].to_numpy()[user_row]),
            _arr(users["region"].to_numpy()[user_row]),
            _arr(users["city"].to_numpy()[user_row]),
        ],
        names=["country", "region", "city"],
    )
    traffic = pa.StructArray.from_arrays(
        [
            _arr(users["campaign"].to_numpy()[user_row]),
            _arr(users["medium"].to_numpy()[user_row]),
            _arr(users["source"].to_numpy()[user_row]),
        ],
        names=["name", "medium", "source"],
    )
    transaction_id = np.full(len(events), None, dtype=object)
    order_no = np.cumsum(is_purchase)[is_purchase]
    transaction_id[is_purchase] = [f"T{n:07d}" for n in order_no]
    ecommerce = pa.StructArray.from_arrays(
        [
            _arr(np.where(is_purchase, revenue, None), type=pa.float64()),
            _arr(transaction_id, type=pa.string()),
            _arr(np.where(is_purchase, qty, None), type=pa.int64()),
        ],
        names=["purchase_revenue", "transaction_id", "total_item_quantity"],
    )

    first_touch = (
        np.datetime64(config.START_DATE, "us").astype("int64")
        + users["first_day"].to_numpy()[user_row].astype("int64") * 86_400_000_000
    )

    return pa.table(
        {
            "event_date": pa.array(event_date),
            "event_timestamp": pa.array(ts, type=pa.int64()),
            "event_name": pa.array(events["event_name"].to_numpy()),
            "event_params": _params_array(events, sessions),
            "user_pseudo_id": pa.array(users["user_pseudo_id"].to_numpy()[user_row]),
            "user_first_touch_timestamp": pa.array(first_touch, type=pa.int64()),
            "device": device,
            "geo": geo,
            "traffic_source": traffic,
            "items": items,
            "ecommerce": ecommerce,
        }
    )


def write_daily_shards(table: pa.Table) -> int:
    for old in config.RAW_DIR.glob("events_*.parquet"):
        old.unlink()
    dates = table.column("event_date").to_pandas()
    for date, group in dates.groupby(dates):
        idx = group.index.to_numpy()
        shard = table.take(pa.array(idx))
        pq.write_table(shard, config.RAW_DIR / f"events_{date}.parquet", compression="zstd")
    return dates.nunique()


def main(n_users: int = N_USERS, seed: int = config.RANDOM_SEED) -> None:
    config.ensure_dirs()
    rng = np.random.default_rng(seed)

    catalog = build_catalog(rng)
    users = build_users(rng, n_users)
    sessions = build_sessions(rng, users)
    sessions = score_funnel(rng, sessions, users, catalog)
    sessions = _loyalty_pass(sessions)
    events = build_events(rng, sessions, users, catalog)
    table = to_arrow(events, sessions, users, catalog, rng)
    n_days = write_daily_shards(table)

    catalog.drop(columns=["view_weight", "atc_lift", "category_index"]).to_csv(config.RAW_DIR / "dim_products.csv", index=False)
    n = len(sessions)
    chain = " ".join(
        f"{flag}={sessions[flag].mean():.3f}"
        for flag in ["viewed_product", "added_to_cart", "viewed_cart", "began_checkout",
                     "added_shipping", "added_payment", "purchased"]
    )
    print(
        f"users={len(users):,} sessions={n:,} events={len(events):,} "
        f"purchases={int(sessions['purchased'].sum()):,} shards={n_days}"
    )
    print(chain)


if __name__ == "__main__":
    main()
