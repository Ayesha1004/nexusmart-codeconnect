"""order_items.csv (315,143 rows). Cross-file repairs (price from product, discount from the
order's code) happen in integrity.py because they need orders and products."""
from __future__ import annotations

import pandas as pd

from .common import Tracker, null_sentinel, parse_quantity, to_number

QTY_PLACEHOLDER = 500    # real data: quantities are 1-6, then 641 lines of exactly 500. It is a placeholder;
                         # integrity.py recovers the true quantity from the order total.
QTY_FLAG_ABOVE = 50      # other large quantities are only counted


def clean_order_items(df: pd.DataFrame):
    t = Tracker("order_items")
    df = t.start(df)

    df = t.drop_exact_duplicates(df)
    for col in ("order_item_id", "order_id", "product_id", "seller_id"):
        df[col] = df[col].str.strip()
    df = t.reject(df, df["order_item_id"].isna(), "MISSING_ID", "order_item_id missing")
    df = t.drop_duplicate_ids(df, "order_item_id")

    # quantities arrive as words ('two') and with the wrong sign ('-3'). Both are real sales lines:
    # converting them recovers ~1,270 lines that were being thrown away (checked against order totals).
    qty, is_word, was_negative = parse_quantity(df["quantity"])
    t.repaired("quantity_word_converted", is_word.sum())
    t.repaired("quantity_negative_made_positive", was_negative.sum())   # DECISION: sign error, not a refund
    df["quantity"] = qty
    unit, bad_price = to_number(df["unit_price"])      # 'Rs. 2,290' -> 2290
    unit, placeholder_price = null_sentinel(unit)
    t.repaired("unit_price_placeholder_9999999", placeholder_price.sum())
    df["unit_price"] = unit
    disc, _ = to_number(df["discount_amount"])
    df["discount_amount"], placeholder_disc = null_sentinel(disc)
    t.repaired("discount_placeholder_9999999", placeholder_disc.sum())

    # still impossible (empty, 0, 2.5): cannot be repaired from anywhere -> reject
    bad_q = df["quantity"].isna() | (df["quantity"] <= 0) | (df["quantity"] % 1 != 0)
    df = t.reject(df, bad_q, "INVALID_QUANTITY", "quantity missing, zero or not a whole number")
    placeholder_q = df["quantity"] == QTY_PLACEHOLDER
    t.repaired("quantity_placeholder_flagged_for_repair", placeholder_q.sum())
    t.repaired("quantity_other_above_flag_threshold", ((df["quantity"] > QTY_FLAG_ABOVE) & ~placeholder_q).sum())
    df["_qty_placeholder"] = placeholder_q                        # temporary: dropped in integrity.py
    df["quantity"] = df["quantity"].where(~placeholder_q).astype("Int64")

    # price missing / <=0 is left as NaN here; integrity.py repairs it from the product list price
    bad_p = df["unit_price"].isna() | (df["unit_price"] <= 0)
    df.loc[bad_p, "unit_price"] = float("nan")
    t.repaired("unit_price_invalid_flagged_for_repair", bad_p.sum())
    return t.finish(df)
