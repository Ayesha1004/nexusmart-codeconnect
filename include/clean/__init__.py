"""Cleaning package. Airflow's `clean` task and the notebooks both call `run_all()`.

    from clean import run_all
    summary = run_all()      # reads RAW_DIR, writes PROCESSED_DIR

Single-file functions (each returns (clean_df, rejects_df)):
    clean_locations, clean_sellers, clean_products, clean_customers, clean_orders,
    clean_order_items, clean_payments, clean_shipping, clean_returns
Cross-file rules: integrity.apply_integrity
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

import pandas as pd

from .common import ID_MAPS, REJECT_COLUMNS, STATS
from .customers import clean_customers
from .integrity import apply_integrity
from .locations import clean_locations
from .order_items import clean_order_items
from .orders import clean_orders
from .payments import clean_payments
from .products import clean_products
from .returns import clean_returns
from .sellers import clean_sellers
from .shipping import clean_shipping

log = logging.getLogger(__name__)

# dependency order: parents before children
CLEANERS = {
    "locations": clean_locations,
    "sellers": clean_sellers,
    "products": clean_products,
    "customers": clean_customers,
    "orders": clean_orders,
    "order_items": clean_order_items,
    "payments": clean_payments,
    "shipping": clean_shipping,
    "returns": clean_returns,
}


def run_all(raw_dir: str | None = None, out_dir: str | None = None) -> dict:
    raw = Path(raw_dir or os.environ.get("RAW_DIR", "data/raw"))
    out = Path(out_dir or os.environ.get("PROCESSED_DIR", "data/processed"))
    out.mkdir(parents=True, exist_ok=True)
    STATS.clear()
    ID_MAPS.clear()

    data, rejects = {}, []
    for name, fn in CLEANERS.items():
        # everything is read as text on purpose: type conversion is a cleaning decision, not pandas' guess
        df = pd.read_csv(raw / f"{name}.csv", dtype=str)
        data[name], rej = fn(df)
        rejects.append(rej)
    data, rej = apply_integrity(data, dict(ID_MAPS))
    rejects.append(rej)

    for name, df in data.items():
        df.to_csv(out / f"{name}.csv", index=False)
    all_rejects = pd.concat([r for r in rejects if not r.empty], ignore_index=True) \
        if any(not r.empty for r in rejects) else pd.DataFrame(columns=REJECT_COLUMNS)
    all_rejects.to_csv(out / "rejects.csv", index=False)
    for key, m in ID_MAPS.items():
        m.to_csv(out / f"{key}_map.csv", index=False)
    stats = pd.DataFrame(STATS)
    stats.to_csv(out / "clean_stats.csv", index=False)

    summary = {r["entity"]: {"rows_in": int(r["rows_in"]), "rows_out": int(r["rows_out"]),
                             "rows_rejected": int(r["rows_rejected"])}
               for r in STATS if r["entity"] in CLEANERS}
    summary["total_rejects"] = int(len(all_rejects))
    log.info("run_all summary: %s", summary)
    return summary
