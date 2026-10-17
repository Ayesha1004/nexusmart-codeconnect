"""Cross-file rules. Runs AFTER every file has been cleaned on its own, because these rules need
final parent tables (e.g. an order is only an 'orphan' once duplicate customers are merged).

Order of steps (each logs a row to the run stats):
  1. re-link orders / order_items to merged customers and products (id maps)
  2. broken references -> Unknown member (kept, revenue is preserved) or quarantine (cannot be linked)
  3. repair order dates from payments / shipping, quarantine what is left
  4. cascade: children of removed orders are quarantined
  5. order_items: repair price from the product list price, reconcile discount with the order's code
  6. returns: orphan lines quarantined, impossible return dates nulled
  7. reconciliation check: order_total vs sum of its lines (logged, not changed)

Rule of thumb used here: if a record's revenue can still be counted correctly, map the broken
reference to Unknown; if the record cannot be attributed at all, quarantine it with a reason code.
"""
from __future__ import annotations

import pandas as pd

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

    # ---- 5. order_items: price repair, discount reconciliation
    list_price = prod.set_index("product_id")["list_price"]
    need = items["unit_price"].isna()
    fixed = items.loc[need, "product_id"].map(list_price)
    items.loc[need, "unit_price"] = fixed
    note("order_items.unit_price_repaired_from_list_price", fixed.notna().sum())
    items = reject(items, items["unit_price"].isna(), "order_items", "INVALID_PRICE",
                   "unit_price missing/<=0 and no product list price to repair from")

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
