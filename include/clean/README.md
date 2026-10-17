# NexusMart cleaning package

One module per CSV, plus one cross-file step. Every cleaner has the same shape:

    clean_df, rejects_df = clean_orders(raw_df)      # raw_df read with dtype=str

Rules for everyone editing a module:
1. Never silently drop a row. Use `t.reject(...)` (reason code + raw record kept) or `t.repaired(...)` (counted).
2. `rows_in == rows_out + rejected` is asserted in `t.finish()`. If it fails, you lost rows somewhere.
3. Value maps live in `mappings.py` (lowercase keys). Add a spelling there, not an `if` in the code.
4. Judgement calls are marked `# DECISION` in the code. The team confirms them (list below).

## Run it

Notebook:
    import sys; sys.path.append("include")
    from clean import run_all
    summary = run_all("data/raw", "data/processed")

Airflow `clean` task: `from clean import run_all; run_all()` (reads RAW_DIR, writes PROCESSED_DIR).
Test: `python tests/test_clean_smoke.py`

Outputs in the processed folder: cleaned CSVs, `rejects.csv`, `customer_map.csv`, `product_map.csv`, `clean_stats.csv`.

## Who owns what
| Module | File | Notes |
|---|---|---|
| locations.py | locations.csv | coordinates outliers, province spellings |
| sellers.py | sellers.csv | rating 0-5, join_date not limited to order window |
| products.py | products.csv | price strings ("Rs. 1,250"), duplicate merge, outliers |
| customers.py | customers.csv | duplicate merge, phone normalisation, birth_year range |
| orders.py | orders.csv | bad dates kept as NaT for repair, discount_pct from code |
| order_items.py | order_items.csv | quantity, price, discount |
| payments.py | payments.csv | duplicate payments, payment_rank |
| shipping.py | shipping.csv | one shipment per order, fee flag |
| returns.py | returns.csv | is_valid_return |
| integrity.py | cross-file | orphans, date repair, discount reconciliation |

## DECISIONS the team must confirm
1. `Shipped` -> `In Transit` (brief lists 4 order statuses).
2. Debit/Credit Card spellings merge into `Card`.
3. Payment status `Complete`/`Success` -> `Paid`.
4. Canonical category name `Grocery` (check against the brief's list).
5. Products are duplicates if normalized name matches and list_price is within 5%.
6. Customers are duplicates if name + (email or phone) + birth_year link them.
7. Line discount is replaced by the order's SAVE<n> percentage when they disagree.
8. Bad order date: repaired from primary payment date, then shipped date; otherwise rejected.
9. birth_year valid range 1930-2010, else null.
10. Quantity <= 0 is rejected (INVALID_QUANTITY).
11. Missing shipping_fee is flagged (`shipping_fee_missing`), not filled.
12. Duplicate payments: keep best by payment_rank Paid > Refunded > Pending > Cancelled, then latest date.
13. Orphan customer/product/seller -> `UNKNOWN` member (revenue kept); orphan order lines/returns -> rejected.
14. Unmapped return status counts as NOT a valid return.
15. A return dated before its order has its return_date nulled.

## Known limits
Tested only on synthetic data (tests/make_sample_data.py). Run it on the real files and read `clean_stats.csv`
and `rejects.csv` before trusting any rule; tune thresholds from what the real data shows.
