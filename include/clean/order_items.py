"""order_items.csv (315,143 rows). Cross-file repairs (price from product, discount from the
order's code) happen in integrity.py because they need orders and products."""
from __future__ import annotations

import pandas as pd

from .common import Tracker, to_number

QTY_FLAG_ABOVE = 50      # DECISION: quantity above this is flagged (not removed). Check the real distribution.


def clean_order_items(df: pd.DataFrame):
    t = Tracker("order_items")
    df = t.start(df)

    df = t.drop_exact_duplicates(df)
    for col in ("order_item_id", "order_id", "product_id", "seller_id"):
        df[col] = df[col].str.strip()
    df = t.reject(df, df["order_item_id"].isna(), "MISSING_ID", "order_item_id missing")
    df = t.drop_duplicate_ids(df, "order_item_id")

    qty, bad_qty = to_number(df["quantity"])
    df["quantity"] = qty
    unit, bad_price = to_number(df["unit_price"])      # 'Rs. 2,290' -> 2290
    df["unit_price"] = unit
    df["discount_amount"], _ = to_number(df["discount_amount"])

    # impossible quantities cannot be repaired from anywhere: reject
    bad_q = df["quantity"].isna() | (df["quantity"] <= 0) | (df["quantity"] % 1 != 0)
    df = t.reject(df, bad_q, "INVALID_QUANTITY", "quantity missing, <=0 or not a whole number")
    t.repaired("quantity_above_flag_threshold", (df["quantity"] > QTY_FLAG_ABOVE).sum())
    df["quantity"] = df["quantity"].astype("Int64")

    # price missing / <=0 is left as NaN here; integrity.py repairs it from the product list price
    bad_p = df["unit_price"].isna() | (df["unit_price"] <= 0)
    df.loc[bad_p, "unit_price"] = float("nan")
    t.repaired("unit_price_invalid_flagged_for_repair", bad_p.sum())
    return t.finish(df)
