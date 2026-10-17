"""customers.csv (45,000 rows). The trickiest file: duplicate customers under different IDs.

Merge rule (never on name alone): two rows are the same person when they share the same
normalized NAME and the same EMAIL, or the same NAME and the same PHONE, and the same birth_year
(a missing birth_year only matches another missing one). Links are transitive. The lowest
customer_id becomes the master; every other id goes to `customer_map` so orders can be re-linked.

DECISION (open): a duplicate pair where only ONE side has a birth_year is not merged by this rule.
Check how many such pairs exist in the profile before relaxing it.
"""
from __future__ import annotations

import pandas as pd

from .common import (ID_MAPS, WINDOW_END, Tracker, UNKNOWN, join_keys, link_by_keys, norm_key,
                     parse_dates, standardize, to_int, to_number)
from .mappings import GENDER

BIRTH_YEAR_RANGE = (1930, 2010)      # DECISION: outside this = implausible
_EMAIL = r"^[\w.+-]+@[\w-]+(\.[\w-]+)+$"


def normalize_phone(s: pd.Series):
    """Digits only; '+92 3xx...' / '3xx...' -> '03xxxxxxxxx'. Anything else -> NaN."""
    d = s.str.replace(r"\D", "", regex=True)
    d = d.str.replace(r"^92(?=3\d{9}$)", "0", regex=True)
    d = d.str.replace(r"^(?=3\d{9}$)", "0", regex=True)
    valid = d.str.fullmatch(r"03\d{9}").fillna(False).astype(bool)
    return d.where(valid), (s.notna() & ~valid)


def clean_customers(df: pd.DataFrame):
    t = Tracker("customers")
    df = t.start(df)

    df = t.drop_exact_duplicates(df)
    df["customer_id"] = df["customer_id"].str.strip()
    df = t.reject(df, df["customer_id"].isna(), "MISSING_ID", "customer_id missing")
    df = t.drop_duplicate_ids(df, "customer_id")

    df["full_name"] = df["full_name"].str.strip().str.replace(r"\s+", " ", regex=True).str.title()
    df["email"] = df["email"].str.strip().str.lower()
    bad_email = df["email"].notna() & ~df["email"].str.match(_EMAIL).fillna(False).astype(bool)
    t.repaired("email_invalid_set_null", bad_email.sum())
    df.loc[bad_email, "email"] = pd.NA
    df["phone"], bad_phone = normalize_phone(df["phone"])
    t.repaired("phone_invalid_set_null", bad_phone.sum())
    df["gender"], unmapped = standardize(df["gender"], GENDER)
    t.repaired("gender_unmapped", unmapped.sum())

    # registration_date can pre-date the order window; only impossible / future dates are errors.
    dates, bad = parse_dates(df["registration_date"])
    future = (dates > WINDOW_END).fillna(False)
    t.repaired("registration_date_unparseable_set_null", bad.sum())
    t.repaired("registration_date_after_period_set_null", future.sum())
    df["registration_date"] = dates.where(~future)

    df["city_id"] = to_int(df["city_id"])
    by, _ = to_number(df["birth_year"])
    out = by.notna() & ~by.between(*BIRTH_YEAR_RANGE)
    t.repaired("birth_year_out_of_range_set_null", out.sum())
    df["birth_year"] = by.where(~out).round().astype("Int64")

    # ---- merge duplicate customers
    name = norm_key(df["full_name"])
    by_key = df["birth_year"].astype(object).where(df["birth_year"].notna(), "?").astype(str)
    group = link_by_keys(df.index,
                         join_keys(name, df["email"], by_key),
                         join_keys(name, df["phone"], by_key))
    df["master_id"] = df.groupby(group)["customer_id"].transform("min")
    ID_MAPS["customer"] = df.loc[df["master_id"] != df["customer_id"], ["customer_id", "master_id"]] \
        .rename(columns={"customer_id": "old_id"}).reset_index(drop=True)
    df = t.reject(df, df["master_id"] != df["customer_id"], "MERGED_DUPLICATE",
                  "same name + email/phone + birth_year; see customer_map")

    return t.finish(df.drop(columns=["master_id"]))
