"""shipping.csv (151,228 rows): one courier charge per ORDER (brief). Dates may fall slightly after
2025-06-30 for late-June orders, so the order window is NOT applied here."""
from __future__ import annotations

import pandas as pd

from .common import Tracker, parse_dates, standardize, to_number
from .mappings import COURIER, DELIVERY_STATUS


def clean_shipping(df: pd.DataFrame):
    t = Tracker("shipping")
    df = t.start(df)

    df = t.drop_exact_duplicates(df)
    df["shipment_id"] = df["shipment_id"].str.strip()
    df["order_id"] = df["order_id"].str.strip()
    df = t.reject(df, df["shipment_id"].isna(), "MISSING_ID", "shipment_id missing")
    df = t.drop_duplicate_ids(df, "shipment_id")
    df = t.reject(df, df["order_id"].duplicated(keep="first"), "DUPLICATE_ORDER_SHIPMENT",
                  "second shipment for the same order; fee is one charge per order")

    df["courier"], unmapped = standardize(df["courier"], COURIER)
    t.repaired("courier_unmapped", unmapped.sum())
    df["delivery_status"], unmapped = standardize(df["delivery_status"], DELIVERY_STATUS)
    t.repaired("delivery_status_unmapped", unmapped.sum())

    shipped, bad_s = parse_dates(df["shipped_date"])
    delivered, bad_d = parse_dates(df["delivered_date"])
    t.repaired("shipped_date_unparseable_set_null", bad_s.sum())
    t.repaired("delivered_date_unparseable_set_null", bad_d.sum())
    backwards = (delivered < shipped).fillna(False)
    t.repaired("delivered_before_shipped_set_null", backwards.sum())   # DECISION: null the delivered date
    df["shipped_date"], df["delivered_date"] = shipped, delivered.where(~backwards)

    fee, bad_fee = to_number(df["shipping_fee"])
    neg = fee < 0
    t.repaired("shipping_fee_negative_set_null", neg.sum())
    # DECISION (open): 9,145 fees are missing. Left null and flagged; decide whether to impute the
    # courier median or treat as 0 before building FactSales.ShippingFee.
    df["shipping_fee"] = fee.where(~neg.fillna(False))
    df["shipping_fee_missing"] = df["shipping_fee"].isna()
    return t.finish(df)
