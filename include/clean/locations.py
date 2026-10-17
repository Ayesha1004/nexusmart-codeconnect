"""locations.csv: city, province, region, tier lookup (650 rows). Clean this file FIRST."""
from __future__ import annotations

import pandas as pd

from .common import Tracker, UNKNOWN, standardize, to_int, to_number
from .mappings import PROVINCE

# Pakistan bounding box (rough). Coordinates outside it are treated as errors.
LAT_RANGE, LON_RANGE = (23.0, 37.5), (60.0, 77.5)


def _tidy_city(s: pd.Series) -> pd.Series:
    s = s.str.strip().str.replace(r"\s+", " ", regex=True)
    shouting = s.str.isupper() | s.str.islower()       # 'KHURDSHAHCHAK', 'saraikhanrah'
    return s.where(~shouting.fillna(False), s.str.title())  # DECISION: cosmetic only, city_id is the key


def clean_locations(df: pd.DataFrame):
    t = Tracker("locations")
    df = t.start(df)

    df = t.drop_exact_duplicates(df)
    df["city_id"] = to_int(df["city_id"])
    df = t.reject(df, df["city_id"].isna(), "MISSING_ID", "city_id missing")
    df = t.drop_duplicate_ids(df, "city_id")

    df["city"] = _tidy_city(df["city"])
    df["province"], unmapped = standardize(df["province"], PROVINCE)
    t.repaired("province_unmapped_or_missing_set_unknown", (df["province"] == UNKNOWN).sum())  # DECISION: cannot infer
    df["region"] = df["region"].str.strip().str.title().fillna(UNKNOWN)

    # 'tier-1', 'Tier 1', 'TIER-1' -> 'Tier-1'
    digit = df["population_tier"].str.extract(r"(\d)")[0]
    df["population_tier"] = ("Tier-" + digit).fillna(UNKNOWN)

    lat, bad_lat = to_number(df["latitude"])
    lon, bad_lon = to_number(df["longitude"])
    out_lat = lat.notna() & ~lat.between(*LAT_RANGE)
    out_lon = lon.notna() & ~lon.between(*LON_RANGE)
    t.repaired("coordinates_outside_pakistan_set_null", (out_lat | out_lon).sum())
    df["latitude"] = lat.where(~(out_lat | out_lon))
    df["longitude"] = lon.where(~(out_lat | out_lon))   # missing coordinates stay null (not needed for revenue)

    return t.finish(df)
