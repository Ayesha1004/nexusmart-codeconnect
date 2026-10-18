"""TEMPLATE: copy this file to <yourfile>.py (e.g. shipping.py), rename the function, fill in the TODOs.

What a cleaning function does
-----------------------------
Takes the raw DataFrame of ONE csv (every column is text) and returns TWO tables:
    clean_df    rows that are usable, with fixed values
    rejects_df  rows removed, each with a reason code and the original record

Golden rules
  1. Never drop a row silently: either t.reject(...) it or fix it and count it with t.repaired(...).
  2. Fix a value if you can be sure; otherwise set it to null/'Unknown' and count it. Never guess.
  3. Spellings go in mappings.py, not in if-statements here.
  4. Mark judgement calls with `# DECISION:` so the team can review them.
  5. t.finish() checks rows_in == rows_out + rejected. If it fails, you lost rows.
"""
from __future__ import annotations

import pandas as pd

from .common import Tracker, parse_dates, standardize, to_number
from .mappings import CHANNEL  # TODO: import the maps you need


def clean_example(df: pd.DataFrame):          # TODO: rename, e.g. clean_shipping
    t = Tracker("example")                    # TODO: entity name, same as the csv name without .csv
    df = t.start(df)                          # logs rows_in, strips whitespace, blank -> NaN

    # 1. exact duplicate rows ------------------------------------------------------------
    df = t.drop_exact_duplicates(df)

    # 2. primary key: missing or repeated ids ---------------------------------------------
    df = t.reject(df, df["example_id"].isna(), "MISSING_ID", "primary key missing")      # TODO column
    df = t.drop_duplicate_ids(df, "example_id")                                           # TODO column

    # 3. categorical text: map every spelling to one canonical value ----------------------
    df["channel"], unmapped = standardize(df["channel"], CHANNEL)                         # TODO column + map
    t.repaired("channel_unmapped", unmapped.sum())     # values not in the map become 'Unknown'

    # 4. numbers: strip 'Rs.', commas, text; then range-check --------------------------
    amount, bad = to_number(df["amount"])                                                 # TODO column
    t.repaired("amount_unparseable", bad.sum())
    negative = amount < 0
    t.repaired("amount_negative_set_null", negative.sum())
    df["amount"] = amount.where(~negative.fillna(False))   # DECISION: negative -> null, not rejected

    # 5. dates: parse the mixed formats; impossible dates (02-30, 00/00/2024) become NaT ---
    dates, bad = parse_dates(df["some_date"])                                             # TODO column
    t.repaired("some_date_unparseable_set_null", bad.sum())
    df["some_date"] = dates

    # 6. file-specific rules go here (see README table for what each file needs) ----------
    # TODO

    return t.finish(df)                       # -> (clean_df, rejects_df), asserts the row counts add up
