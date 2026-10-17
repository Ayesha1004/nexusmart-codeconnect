"""sellers.csv (420 rows). Needs locations cleaned first for the city check (done in integrity.py)."""
from __future__ import annotations

import pandas as pd

from .common import WINDOW_END, Tracker, UNKNOWN, parse_dates, standardize, to_int, to_number
from .mappings import SELLER_TIER

RATING_RANGE = (0.0, 5.0)   # DECISION: seen 11.0, so ratings outside 0-5 are errors


def clean_sellers(df: pd.DataFrame):
    t = Tracker("sellers")
    df = t.start(df)

    df = t.drop_exact_duplicates(df)
    df["seller_id"] = df["seller_id"].str.strip()
    df = t.reject(df, df["seller_id"].isna(), "MISSING_ID", "seller_id missing")
    df = t.drop_duplicate_ids(df, "seller_id")

    df["seller_name"] = df["seller_name"].str.strip().str.replace(r"\s+", " ", regex=True)
    df["seller_tier"], unmapped = standardize(df["seller_tier"], SELLER_TIER)
    t.repaired("seller_tier_unmapped", unmapped.sum())

    # join_date is NOT limited to the order window (sellers can join earlier). Only impossible
    # dates and dates after the data period are errors. Keep the row, null the date.
    dates, bad = parse_dates(df["join_date"])
    future = dates > WINDOW_END
    t.repaired("join_date_unparseable_set_null", bad.sum())
    t.repaired("join_date_after_period_set_null", future.sum())
    df["join_date"] = dates.where(~future.fillna(False))

    rating, bad_rating = to_number(df["rating"])
    out = rating.notna() & ~rating.between(*RATING_RANGE)
    t.repaired("rating_out_of_range_set_null", (out | bad_rating).sum())
    df["rating"] = rating.where(~out)

    df["city_id"] = to_int(df["city_id"])
    return t.finish(df)
