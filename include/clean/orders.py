"""orders.csv (163,200 rows).

Stage 1 (this file): single-file rules. Orders whose date is impossible or outside the window
are KEPT with order_date = NaT and flagged `order_date_issue`; integrity.py tries to repair them
from payments/shipping and only then quarantines what is left (so we do not reject an order
we could have saved, and children can be cascaded in one place).
"""
from __future__ import annotations

import pandas as pd

from .common import WINDOW_END, WINDOW_START, Tracker, parse_dates, standardize, to_int, to_number
from .mappings import CHANNEL, ORDER_STATUS


def clean_orders(df: pd.DataFrame):
    t = Tracker("orders")
    df = t.start(df)

    df = t.drop_exact_duplicates(df)        # 3,200 in the profile; affects the cancellation-rate denominator
    df["order_id"] = df["order_id"].str.strip()
    df = t.reject(df, df["order_id"].isna(), "MISSING_ID", "order_id missing")
    df = t.drop_duplicate_ids(df, "order_id")
    df["customer_id"] = df["customer_id"].str.strip()

    dates, bad = parse_dates(df["order_date"])
    outside = dates.notna() & ~dates.between(WINDOW_START, WINDOW_END)
    df["order_date_raw"] = df["order_date"]
    df["order_date_issue"] = ""
    df.loc[bad, "order_date_issue"] = "UNPARSEABLE"
    df.loc[outside, "order_date_issue"] = "OUT_OF_RANGE"
    df["order_date"] = dates.where(~outside)
    t.repaired("order_date_flagged_for_repair", bad.sum() + outside.sum())

    df["order_status"], unmapped = standardize(df["order_status"], ORDER_STATUS)
    t.repaired("order_status_unmapped", unmapped.sum())
    df["channel"], unmapped = standardize(df["channel"], CHANNEL)
    t.repaired("channel_unmapped", unmapped.sum())

    df["ship_city_id"] = to_int(df["ship_city_id"])      # null stays null -> Unknown location later (do not guess)

    # discount_code 'Save15', ' SAVE15' -> 15 (percent). Empty code = no discount (brief).
    code = df["discount_code"].str.strip().str.upper()
    pct = code.str.extract(r"^SAVE(\d+)$")[0]
    t.repaired("discount_code_unparseable", (code.notna() & pct.isna()).sum())
    df["discount_code"] = code
    df["discount_pct"] = pd.to_numeric(pct, errors="coerce").fillna(0)

    total, bad_total = to_number(df["order_total"])
    t.repaired("order_total_unparseable", bad_total.sum())
    df["order_total"] = total                      # used for a reconciliation check, not for revenue
    return t.finish(df)
