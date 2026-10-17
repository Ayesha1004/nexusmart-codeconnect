"""payments.csv (168,111 rows). An order can have several payment rows: `payment_rank == 1` marks the
single row used for the fact table's PaymentMethod (DECISION below)."""
from __future__ import annotations

import pandas as pd

from .common import Tracker, parse_dates, standardize, to_number
from .mappings import PAYMENT_METHOD, PAYMENT_STATUS

# DECISION: which payment represents the order? Paid first, then refunded, pending, cancelled;
# within the same status the latest payment_date.
STATUS_PRIORITY = {"Paid": 0, "Refunded": 1, "Pending": 2, "Cancelled": 3}


def clean_payments(df: pd.DataFrame):
    t = Tracker("payments")
    df = t.start(df)

    df = t.drop_exact_duplicates(df)        # 3,296 in the profile
    df["payment_id"] = df["payment_id"].str.strip()
    df["order_id"] = df["order_id"].str.strip()
    df = t.reject(df, df["payment_id"].isna(), "MISSING_ID", "payment_id missing")
    df = t.drop_duplicate_ids(df, "payment_id")

    df["payment_method"], unmapped = standardize(df["payment_method"], PAYMENT_METHOD)
    t.repaired("payment_method_unmapped", unmapped.sum())
    df["payment_status"], unmapped = standardize(df["payment_status"], PAYMENT_STATUS)
    t.repaired("payment_status_unmapped", unmapped.sum())
    df["amount"], bad = to_number(df["amount"])
    t.repaired("amount_unparseable", bad.sum())

    # payment_date may legitimately fall just after the order window; only impossible dates are errors
    dates, bad = parse_dates(df["payment_date"])
    t.repaired("payment_date_unparseable_set_null", bad.sum())
    df["payment_date"] = dates

    prio = df["payment_status"].map(STATUS_PRIORITY).fillna(9)
    ranked = df.assign(_prio=prio).sort_values(["order_id", "_prio", "payment_date"],
                                               ascending=[True, True, False], na_position="last")
    df["payment_rank"] = ranked.groupby("order_id").cumcount().reindex(df.index) + 1
    return t.finish(df)
