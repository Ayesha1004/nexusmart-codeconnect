"""Cross-file rules. Runs AFTER every file has been cleaned on its own, because these rules need
final parent tables (e.g. an order is only an 'orphan' once duplicate customers are merged).

Order of steps (each logs a row to the run stats):
  1. re-link orders / order_items to merged customers and products (id maps)
  2. broken references -> Unknown member (kept, revenue is preserved) or quarantine (cannot be linked)
  3. repair order dates from payments / shipping, quarantine what is left
  4. cascade: children of removed orders are quarantined
  5. order_items: repair price (x100 / US-dollar / placeholder), recover placeholder quantities from the
     order total, reconcile discount with the order's code; fill missing shipping fees
  6. returns: orphan lines quarantined, impossible return dates nulled
  7. reconciliation check: order_total vs sum of its lines (logged, not changed)

Rule of thumb used here: if a record's revenue can still be counted correctly, map the broken
reference to Unknown; if the record cannot be attributed at all, quarantine it with a reason code.
"""
from __future__ import annotations

import pandas as pd

USD_TO_PKR = 280   # DECISION: implied by 44 single-line orders with dollar prices (median 279.9)
PRICE_MIN, PRICE_MAX = 50, 70_000   # real list prices run 100-62,530; lines sell at 0.9-1.1x list

from .common import (UNKNOWN_ID, WINDOW_END, WINDOW_START, log_step, make_rejects)


def apply_integrity(data: dict, id_maps: dict):
    rejects: list[pd.DataFrame] = []

    def reject(df: pd.DataFrame, mask, entity: str, reason: str, detail: str = "") -> pd.DataFrame:
        mask = pd.Series(mask, index=df.index).fillna(False).astype(bool)
        n = int(mask.sum())
        if n:
            rejects.append(make_rejects(df[mask], f"{entity}.csv", reason, detail + " (cleaned values shown)"))
            log_step(f"integrity:{entity}:{reason}", len(df), len(df) - n, n)
        return df[~mask].copy()

    def note(name: str, n) -> None:
        n = int(n)
        if n:
            log_step(f"integrity:{name}", n, n, 0)

    def remap(series: pd.Series, id_map: pd.DataFrame | None) -> pd.Series:
        if id_map is None or id_map.empty:
            return series
        return series.map(dict(zip(id_map["old_id"], id_map["master_id"]))).fillna(series)

    loc, sel, prod, cust = data["locations"], data["sellers"], data["products"], data["customers"]
    orders, items, pay, ship, ret = (data["orders"], data["order_items"], data["payments"],
                                     data["shipping"], data["returns"])

    # ---- 1/2. merged ids, then broken references -> Unknown
    orders["customer_id"] = remap(orders["customer_id"], id_maps.get("customer"))
    items["product_id"] = remap(items["product_id"], id_maps.get("product"))

    orphan = ~orders["customer_id"].isin(cust["customer_id"])
    orders["customer_orphan"] = orphan
    orders.loc[orphan, "customer_id"] = UNKNOWN_ID
    note("orders.customer_mapped_to_unknown", orphan.sum())

    orphan = ~items["product_id"].isin(prod["product_id"])
    items["product_orphan"] = orphan
    items.loc[orphan, "product_id"] = UNKNOWN_ID
    note("order_items.product_mapped_to_unknown", orphan.sum())

    orphan = ~items["seller_id"].isin(sel["seller_id"])
    items.loc[orphan, "seller_id"] = UNKNOWN_ID
    note("order_items.seller_mapped_to_unknown", orphan.sum())

    for df, col, name in ((orders, "ship_city_id", "orders.ship_city"), (cust, "city_id", "customers.city"),
                          (sel, "city_id", "sellers.city")):
        orphan = df[col].notna() & ~df[col].isin(loc["city_id"])
        df.loc[orphan, col] = pd.NA
        note(f"{name}_unknown", orphan.sum())                 # null location -> Unknown member in DimLocation

    # ---- 3. order dates: repair from other data, quarantine the rest
    need = orders["order_date"].isna()
    primary_pay = pay[pay["payment_rank"] == 1].set_index("order_id")["payment_date"]
    shipped = ship.set_index("order_id")["shipped_date"]
    by_pay = orders.loc[need, "order_id"].map(primary_pay)
    by_ship = orders.loc[need, "order_id"].map(shipped)
    in_window = lambda s: s.between(WINDOW_START, WINDOW_END)     # noqa: E731
    # DECISION: payment date first, then shipped date. Validate on orders with a good date
    # (how often does payment_date == order_date?) before trusting this rule.
    repair = by_pay.where(in_window(by_pay), by_ship.where(in_window(by_ship)))
    orders.loc[need, "order_date"] = repair
    note("orders.order_date_repaired", repair.notna().sum())
    orders = reject(orders, orders["order_date"].isna(), "orders", "ORDER_DATE_UNREPAIRABLE",
                    "date impossible or outside 2024-01-01..2025-06-30 and no payment/shipping date to repair from")

    # ---- 4. children of removed orders
    valid_orders = set(orders["order_id"])
    items = reject(items, ~items["order_id"].isin(valid_orders), "order_items", "ORPHAN_ORDER",
                   "order missing or quarantined")
    pay = reject(pay, ~pay["order_id"].isin(valid_orders), "payments", "ORPHAN_ORDER", "order missing or quarantined")
    ship = reject(ship, ~ship["order_id"].isin(valid_orders), "shipping", "ORPHAN_ORDER",
                  "order missing or quarantined")

    # ---- 5. order_items: price repair, quantity repair, discount reconciliation
    # In the real data a normal line is priced at 0.9-1.1 x the product's list price. Three kinds of
    # corruption were found by comparing with the list price AND confirmed against the order totals:
    #   price x100            (ratio ~100)   -> divide by 100            (54 of 56 single-line orders reconcile)
    #   price in US dollars   (ratio ~0.0036)-> multiply by 280 PKR/USD  (implied rate 279.9, very tight)
    #   9,999,999 placeholder / anything else implausible -> take the product's list price
    list_price = prod.set_index("product_id")["list_price"]
    # Reference price per line = the product's list price. If the list price itself was a placeholder
    # (null after cleaning), use the median of that product's other plausible line prices instead.
    plausible = items["unit_price"].between(PRICE_MIN, PRICE_MAX)
    line_median = items[plausible & (items["product_id"] != UNKNOWN_ID)].groupby("product_id")["unit_price"].median()
    ref = items["product_id"].map(list_price).fillna(items["product_id"].map(line_median))

    ratio = items["unit_price"] / ref
    x100 = ratio.between(50, 200).fillna(False)
    usd = ratio.between(0.001, 0.01).fillna(False)
    # No reference at all (Unknown product): only extreme values can be recognised, using the real
    # price range (list prices run 100-62,530).
    no_ref = ref.isna() & items["unit_price"].notna()
    x100 |= no_ref & (items["unit_price"] > PRICE_MAX) & (items["unit_price"] / 100).between(PRICE_MIN, PRICE_MAX)
    usd |= no_ref & (items["unit_price"] < PRICE_MIN) & (items["unit_price"] * USD_TO_PKR).between(PRICE_MIN, PRICE_MAX)
    items.loc[x100, "unit_price"] = items.loc[x100, "unit_price"] / 100
    items.loc[usd, "unit_price"] = (items.loc[usd, "unit_price"] * USD_TO_PKR).round()
    note("order_items.unit_price_x100_divided", x100.sum())
    note("order_items.unit_price_usd_converted_to_pkr", usd.sum())
    ratio = items["unit_price"] / ref
    implausible = ((ratio < 0.5) | (ratio > 2)).fillna(False)
    implausible |= ref.isna() & ~items["unit_price"].between(PRICE_MIN, PRICE_MAX) & items["unit_price"].notna()
    items.loc[implausible, "unit_price"] = float("nan")
    note("order_items.unit_price_implausible_set_for_repair", implausible.sum())

    need = items["unit_price"].isna()
    fixed = ref[need]
    items.loc[need, "unit_price"] = fixed
    note("order_items.unit_price_repaired_from_list_price", fixed.notna().sum())
    items = reject(items, items["unit_price"].isna(), "order_items", "INVALID_PRICE",
                   "unit_price missing/placeholder and no product list price to repair from")

    # quantity placeholder (500): the order total is the only place the true quantity still exists.
    #   total = (sum of other lines' gross + qty * price) * (1 - discount%)  ->  solve for qty
    # Accepted only if the answer is a whole number 1-10; otherwise 1 (the most common quantity).
    order_info = orders.set_index("order_id")
    ph = items["_qty_placeholder"].fillna(False).astype(bool)
    pct_o = items["order_id"].map(order_info["discount_pct"]).fillna(0)
    ot = items["order_id"].map(order_info["order_total"])
    gross_known = (items["quantity"].astype("float64") * items["unit_price"]).where(~ph)
    other_gross = gross_known.groupby(items["order_id"]).transform("sum")
    n_ph = ph.groupby(items["order_id"]).transform("sum")
    implied = (ot / (1 - pct_o / 100) - other_gross) / items["unit_price"]
    q = implied.round()
    solved = ph & (n_ph == 1) & ot.notna() & q.between(1, 10) & ((implied - q).abs() <= 0.15)
    items.loc[solved, "quantity"] = q[solved].astype("Int64")
    fallback = ph & ~solved
    items.loc[fallback, "quantity"] = 1                         # DECISION: unknown quantity -> 1
    note("order_items.quantity_placeholder_solved_from_order_total", solved.sum())
    note("order_items.quantity_placeholder_set_to_1", fallback.sum())
    items["quantity"] = items["quantity"].astype("Int64")
    items = items.drop(columns="_qty_placeholder")

    gross = items["quantity"].astype(float) * items["unit_price"]
    pct = items["order_id"].map(orders.set_index("order_id")["discount_pct"]).fillna(0)
    expected = (gross * pct / 100).round()
    disc = items["discount_amount"]
    # DECISION: the order-level code is the source of truth (the profile shows every valid line
    # discount equals its order's SAVE<n> percentage); line values that disagree are replaced.
    missing, over, off = disc.isna(), disc > gross, (disc - expected).abs() > 1
    items["discount_amount"] = disc.where(~(missing | over | off), expected)
    note("order_items.discount_missing_recomputed", missing.sum())
    note("order_items.discount_above_gross_recomputed", (over & ~missing).sum())
    note("order_items.discount_mismatch_recomputed", (off & ~missing & ~over).sum())

    # shipping fee: missing/invalid fees get the typical fee for an order of the same value
    # (real data: median fee rises from ~258 to ~944 with order size; courier makes no difference).
    line_net = items["quantity"].astype(float) * items["unit_price"] - items["discount_amount"]
    order_net = line_net.groupby(items["order_id"]).sum()
    ship_net = ship["order_id"].map(order_net)
    have = ship["shipping_fee"].notna() & ship_net.notna()
    edges = pd.qcut(ship_net[have], 10, duplicates="drop", retbins=True)[1]
    edges[0], edges[-1] = -float("inf"), float("inf")
    bucket = pd.cut(ship_net, edges).astype(object)
    typical = ship.loc[have, "shipping_fee"].groupby(bucket[have]).median().to_dict()
    missing_fee = ship["shipping_fee"].isna()
    fill = bucket.map(typical).astype(float).fillna(ship["shipping_fee"].median())
    ship.loc[missing_fee, "shipping_fee"] = fill[missing_fee].round()
    note("shipping.fee_filled_with_typical_fee_for_order_size", missing_fee.sum())   # flag column stays True

    # ---- 6. returns
    known_items = set(items["order_item_id"])
    ret = reject(ret, ~ret["order_item_id"].isin(known_items), "returns", "ORPHAN_ORDER_ITEM",
                 "order line missing or quarantined")
    order_date = ret["order_item_id"].map(items.set_index("order_item_id")["order_id"]) \
        .map(orders.set_index("order_id")["order_date"])
    before = (ret["return_date"] < order_date).fillna(False)
    ret.loc[before, "return_date"] = pd.NaT      # DECISION: a return cannot pre-date its order
    note("returns.return_date_before_order_set_null", before.sum())

    # ---- 7. reconciliation check (logged only): order_total should equal the sum of its lines
    net = (items["quantity"].astype(float) * items["unit_price"] - items["discount_amount"]) \
        .groupby(items["order_id"]).sum()
    calc = orders["order_id"].map(net)
    mismatch = orders["order_total"].notna() & calc.notna() & ((orders["order_total"] - calc).abs() > 1)
    note("CHECK:orders_total_differs_from_sum_of_lines", mismatch.sum())
    note("CHECK:orders_without_any_line", calc.isna().sum())

    data.update(orders=orders, order_items=items, payments=pay, shipping=ship, returns=ret,
                customers=cust, sellers=sel)
    out_rejects = pd.concat(rejects, ignore_index=True) if rejects else pd.DataFrame()
    return {k: v.reset_index(drop=True) for k, v in data.items()}, out_rejects
