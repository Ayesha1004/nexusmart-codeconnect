"""products.csv (3,200 rows). Standardizes categories and merges duplicate products.

Duplicate products show up as the same product name under a second product_id with a slightly
different list_price and a different seller (P01407 / P03165 in the profile). Merge rule:
  same normalized name (suffixes like ' - New', '(2024)', 'Original' removed)
  AND list prices within PRICE_TOLERANCE of each other (or one price missing).
The lowest product_id becomes the master. Never match on name alone: two different
products can share a name, which is why the price check is part of the rule.
"""
from __future__ import annotations

import pandas as pd

from .common import (ID_MAPS, Tracker, UNKNOWN, UnionFind, norm_key, standardize, to_number)
from .mappings import CATEGORY

PRICE_TOLERANCE = 0.05      # DECISION: 5%. The profiled pairs differ by 0.4% to 3%.
_SUFFIX = r"\s*(?:-\s*new|\(\d{4}\)|original)\s*$"


def _name_key(names: pd.Series) -> pd.Series:
    key = norm_key(names)
    for _ in range(3):                       # a name can carry more than one suffix
        key = key.str.replace(_SUFFIX, "", regex=True)
    return key


def clean_products(df: pd.DataFrame):
    t = Tracker("products")
    df = t.start(df)

    df = t.drop_exact_duplicates(df)
    df["product_id"] = df["product_id"].str.strip()
    df = t.reject(df, df["product_id"].isna(), "MISSING_ID", "product_id missing")
    df = t.drop_duplicate_ids(df, "product_id")

    df["product_name"] = df["product_name"].str.strip().str.replace(r"\s+", " ", regex=True)
    df["category"], unmapped = standardize(df["category"], CATEGORY)
    t.repaired("category_unmapped", unmapped.sum())
    df["sub_category"] = df["sub_category"].str.strip().fillna(UNKNOWN)   # cannot be inferred reliably
    df["seller_id"] = df["seller_id"].str.strip()

    # brand = first word of the name when it is a known brand (repair from other data)
    known = set(df["brand"].dropna().str.strip())
    first_word = df["product_name"].str.split().str[0]
    missing = df["brand"].isna()
    fill = missing & first_word.isin(known)
    df.loc[fill, "brand"] = first_word[fill]
    t.repaired("brand_filled_from_product_name", fill.sum())
    df["brand"] = df["brand"].str.strip().fillna(UNKNOWN)

    list_price, bad_lp = to_number(df["list_price"])
    cost, bad_cp = to_number(df["cost_price"])
    weight, _ = to_number(df["weight_kg"])
    list_price = list_price.where(list_price > 0)
    t.repaired("list_price_invalid_set_null", (list_price.isna() & df["list_price"].notna()).sum())
    weight_bad = weight <= 0                                 # seen -1.00
    t.repaired("weight_invalid_set_null", weight_bad.sum())
    weight = weight.where(~weight_bad.fillna(False))
    cost_bad = (cost <= 0) | (cost > list_price * 1.0)       # DECISION: cost above list price = error (P03085)
    t.repaired("cost_price_invalid_set_null", cost_bad.fillna(False).sum())
    cost = cost.where(~cost_bad.fillna(False))
    df["list_price"], df["cost_price"], df["weight_kg"] = list_price, cost, weight

    # ---- merge duplicates
    df["_name_key"] = _name_key(df["product_name"])
    uf = UnionFind(df.index)
    for _, grp in df[df["_name_key"].duplicated(keep=False)].groupby("_name_key"):
        rows = list(grp.index)
        for i, a in enumerate(rows):
            for b in rows[i + 1:]:
                pa, pb = df.at[a, "list_price"], df.at[b, "list_price"]
                if pd.isna(pa) or pd.isna(pb) or abs(pa - pb) / max(pa, pb) <= PRICE_TOLERANCE:
                    uf.union(a, b)
    group = uf.labels(df.index)
    df["master_id"] = df.groupby(group)["product_id"].transform("min")

    # a master with a missing/invalid cost or weight borrows it from its duplicates
    for col in ("cost_price", "weight_kg"):
        borrowed = df.groupby(group)[col].transform("first")      # first non-null value in the group
        take = df[col].isna() & borrowed.notna() & (df["master_id"] == df["product_id"])
        t.repaired(f"{col}_filled_from_duplicate", take.sum())
        df.loc[take, col] = borrowed[take]

    ID_MAPS["product"] = df.loc[df["master_id"] != df["product_id"], ["product_id", "master_id"]] \
        .rename(columns={"product_id": "old_id"}).reset_index(drop=True)
    df = t.reject(df, df["master_id"] != df["product_id"], "MERGED_DUPLICATE",
                  "same name and price within tolerance; see product_map")
    return t.finish(df.drop(columns=["_name_key", "master_id"]))
