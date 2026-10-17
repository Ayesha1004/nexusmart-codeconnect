"""returns.csv (16,048 rows). A 'Rejected' (or 'Declined') return is NOT a valid return (brief):
it stays in the table with is_valid_return = False so it can still be counted/audited, and the fact
table must only use rows with is_valid_return = True."""
from __future__ import annotations

import pandas as pd

from .common import WINDOW_START, Tracker, parse_dates, standardize, to_number
from .mappings import RETURN_REASON, RETURN_STATUS


def clean_returns(df: pd.DataFrame):
    t = Tracker("returns")
    df = t.start(df)

    df = t.drop_exact_duplicates(df)
    df["return_id"] = df["return_id"].str.strip()
    df["order_item_id"] = df["order_item_id"].str.strip()
    df = t.reject(df, df["return_id"].isna(), "MISSING_ID", "return_id missing")
    df = t.drop_duplicate_ids(df, "return_id")

    df["return_status"], unmapped = standardize(df["return_status"], RETURN_STATUS)
    t.repaired("return_status_unmapped", unmapped.sum())
    df["return_reason"], unmapped = standardize(df["return_reason"], RETURN_REASON)   # missing -> Unknown
    t.repaired("return_reason_unmapped", unmapped.sum())
    df["is_valid_return"] = df["return_status"].isin(["Approved", "Refunded"])
    # DECISION: a status that could not be mapped (-> Unknown) is NOT treated as a valid return.

    dates, bad = parse_dates(df["return_date"])
    t.repaired("return_date_unparseable_set_null", bad.sum())
    early = (dates < WINDOW_START).fillna(False)        # a return cannot pre-date the first possible order
    t.repaired("return_date_before_period_set_null", early.sum())
    df["return_date"] = dates.where(~early)

    refund, bad_refund = to_number(df["refund_amount"])
    t.repaired("refund_amount_unparseable", bad_refund.sum())
    neg = refund < 0
    t.repaired("refund_amount_negative_set_null", neg.sum())
    df["refund_amount"] = refund.where(~neg.fillna(False))
    return t.finish(df)
