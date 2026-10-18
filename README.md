# NexusMart Data Analytics Pipeline

An automated, end-to-end analytics pipeline for **NexusMart**, a Pakistani online marketplace (400+ sellers, 12 product categories, 40 cities). Built for the **CODE // CONNECT '26 Datathon**.

Raw CSV files from nine business systems are profiled, cleaned and standardized with Python, loaded into a PostgreSQL star schema, and orchestrated with Apache Airflow. A Power BI dashboard on top of the warehouse is planned (see [Power BI Dashboard](#power-bi-dashboard)).

**Team:** `<names and university>`

---

## Table of Contents

1. [Architecture](#architecture)
2. [Tech Stack](#tech-stack)
3. [Repository Structure](#repository-structure)
4. [Setup and Run](#setup-and-run)
5. [Airflow Pipeline](#airflow-pipeline)
6. [Data Model (Star Schema)](#data-model-star-schema)
7. [Data Cleaning Rules](#data-cleaning-rules)
8. [Business Metric Definitions](#business-metric-definitions)
9. [Power BI Dashboard](#power-bi-dashboard)
10. [Design Decisions](#design-decisions)
11. [Known Limitations](#known-limitations)
12. [Deliverables Checklist](#deliverables-checklist)

---

## Architecture

```
 Raw CSV files (9 files, ~860k rows, Jan 2024 - Jun 2025)
        |
        v
 Apache Airflow  (orchestration, retries, logging)
        |
        v
 Python  (profiling, cleaning, standardization, validation)
        |
        v
 PostgreSQL warehouse  (staging -> star schema: 1 fact + 5 dimensions)
        |
        v
 Power BI  (planned: dashboard connected to warehouse tables)
        |
        v
 Business insights and recommendations
```

Everything runs locally through Docker Compose: an Airflow cluster (CeleryExecutor with Redis and a metadata Postgres) plus a separate **warehouse** Postgres container.

## Tech Stack

| Technology | Purpose |
|---|---|
| Python (pandas, SQLAlchemy, psycopg2, pyarrow) | Profiling, cleaning, transformation, validation |
| Apache Airflow 3.3.2 | Pipeline automation and monitoring |
| PostgreSQL 16 | Warehouse storage |
| SQL | Schema design, dimension and fact builds, verification queries |
| Power BI | Dashboard and reporting (pending) |
| Docker Compose | Reproducible environment |

## Repository Structure

```
nexusmart-codeconnect/
├── config/              # Airflow configuration (airflow.cfg)
├── dags/
│   └── nexusmart_pipeline.py   # The single Airflow DAG
├── data/
│   ├── raw/             # Input CSVs (place provided dataset here; git-ignored)
│   ├── processed/       # Cleaned CSVs, rejects.csv, id maps, clean_stats.csv (generated; git-ignored)
│   └── export/          # CSV snapshots of the star schema tables (Dim* and FactSales)
├── docs/                # Profiling and data-quality outputs (dq_*.csv), metric reconciliation
├── include/
│   ├── clean/           # Cleaning package: one module per CSV + integrity.py (cross-file rules)
│   └── sql/             # 00_reset, 01_schema, 02_dimensions, 03_fact_sales, load_staging, verify_star_v2
├── notebooks/           # Profiling/cleaning notebooks and metric_reconciliation.ipynb
├── powerbi/             # Reserved for the dashboard (.pbix and PDF export), not yet populated
├── .env.example         # Environment variable template
├── Dockerfile           # Extended Airflow image (installs requirements.txt)
├── docker-compose.yml   # Airflow + warehouse environment
└── requirements.txt     # Python dependencies
```

## Setup and Run

### Prerequisites

- Docker Desktop (or Docker Engine with the Compose plugin)
- At least 4 GB RAM and 2 CPUs allocated to Docker, about 10 GB free disk
- The nine provided CSV files
- Power BI Desktop (Windows)

### 1. Clone the repository

```bash
git clone https://github.com/Ayesha1004/nexusmart-codeconnect.git
cd nexusmart-codeconnect
```

### 2. Add the raw data

Copy the nine CSV files into `data/raw/`:

```
customers.csv  products.csv  sellers.csv  locations.csv  orders.csv
order_items.csv  payments.csv  shipping.csv  returns.csv
```

### 3. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` and set:

| Variable | Description |
|---|---|
| `AIRFLOW_UID` | User ID for Airflow containers (`50000` default; use `id -u` on Linux) |
| `WH_USER` / `WH_PASSWORD` / `WH_DB` | Warehouse database credentials (template values: `nexus` / `change_me` / `nexusmart`; change the password) |
| `FERNET_KEY` | Required by Airflow; **not in `.env.example`, add it yourself** (generate with the command below) |

`RAW_DIR` (`/opt/airflow/data/raw`), `PROCESSED_DIR` (`/opt/airflow/data/processed`) and `WAREHOUSE_URL` are set inside `docker-compose.yml` from these values, so they do not need to be edited. `./data` is mounted into the containers at `/opt/airflow/data`.

Generate a Fernet key:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Warehouse credentials and file paths are read from environment variables, never hard-coded in the DAG or SQL.

### 4. Start the environment

```bash
docker compose up airflow-init
docker compose up -d
```

### 5. Create the warehouse tables (once, on a fresh warehouse)

The pipeline truncates and fills existing tables, so the schema must exist before the first run. Apply it to the warehouse container (safe to repeat, it uses `IF NOT EXISTS`):

```bash
docker compose exec -T warehouse sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < include/sql/01_schema.sql
```

On Windows PowerShell the `<` redirect is not supported; pipe the file in instead:

```powershell
Get-Content include/sql/01_schema.sql | docker compose exec -T warehouse sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

### 6. Run the pipeline

1. Open the Airflow UI at **http://localhost:8080** (login `airflow` / `airflow`).
2. Unpause the DAG `nexusmart_pipeline` (DAGs are paused at creation) and trigger it manually (it has no schedule).
3. Wait for all eight tasks to turn green.

### 7. Verify the warehouse (optional)

`verify_star_v2.sql` reports PASS / FAIL / REVIEW per check (row counts, net amount, returns, shipping fee, unknown members):

```bash
docker compose exec -T warehouse sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < include/sql/verify_star_v2.sql
```

PowerShell:

```powershell
Get-Content include/sql/verify_star_v2.sql | docker compose exec -T warehouse sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

### 8. Connect to the warehouse

| Setting | Value |
|---|---|
| Host | `localhost` |
| Port | `5433` |
| Database | value of `WH_DB` |
| User / Password | values of `WH_USER` / `WH_PASSWORD` |

Use these details in Power BI (**Get Data > PostgreSQL database**) or any SQL client.

### 9. Open the dashboard

PowerBI- NexusMart.pbix in the PowerBI(desktop)

### Stopping and resetting

```bash
docker compose down        # stop containers, keep data
docker compose down -v     # stop and delete all volumes (full reset; repeat step 5 afterwards)
```

## Airflow Pipeline

DAG id: **`nexusmart_pipeline`** (`dags/nexusmart_pipeline.py`). Manual trigger, one linear chain of eight tasks:

| Task | Responsibility |
|---|---|
| `extract` | Check that all nine raw CSVs are present in `RAW_DIR` |
| `validate_raw` | Check each CSV has a readable header and at least one data row |
| `clean` | Run the cleaning package (`include/clean`, `run_all`): standardize, repair, quarantine; write cleaned CSVs, `rejects.csv`, id maps and `clean_stats.csv` to `PROCESSED_DIR` |
| `reset_database` | Run `00_reset.sql`: empty staging and fact, delete all dimension rows except the Unknown members |
| `load_staging_task` | `COPY` the nine cleaned CSVs into the `stg_*` tables (table-to-file pairs come from `load_staging.sql`) |
| `build_dimensions` | Run `02_dimensions.sql`: build DimDate, DimLocation, DimCustomer, DimProduct, DimSeller |
| `build_fact` | Run `03_fact_sales.sql`: populate `FactSales`, with returns aggregated per order line |
| `quality_checks` | Run integrity checks and fail the run if any is violated |

Pipeline properties:

- **Idempotent:** every run rebuilds staging, fact and dimensions from the current cleaned CSVs (see [Design Decisions](#design-decisions)), so repeated runs give the same result and create no duplicates.
- **Retries and error handling:** each task retries twice with a 1-minute delay; the SQL tasks roll back on error; quality-check failures fail the run immediately.
- **Logging:** `clean` logs rows in, out and rejected per entity (also saved in `clean_stats.csv`); `build_dimensions` and `build_fact` log row counts; `load_staging_task` logs each table loaded; `quality_checks` logs every check result.
- **Quality gates:** zero-tolerance. `quality_checks` fails the run (`AirflowFailException`) if any dimension is empty or any of these returns a non-zero value:
  - `FactSales` is empty
  - `FactSales` row count differs from `stg_order_items`
  - duplicate `OrderItemID` in the fact
  - a null key or id (`OrderItemID`, `OrderID`, `DateKey`, `CustomerKey`, `ProductKey`, `SellerKey`, `LocationKey`)
  - a fact key with no matching row in DimCustomer, DimProduct, DimSeller, DimLocation or DimDate (order date and return date)
  - an order whose allocated `ShippingFee` does not add up to its single courier charge
- **No hard-coded warehouse secrets:** paths and warehouse credentials come from environment variables (see the limitations section for the Airflow development defaults).

## Data Model (Star Schema)

A single star schema with one fact table and five unlinked dimension tables. DDL: `include/sql/01_schema.sql`. Diagram: *pending* (to be added under `docs/`).

**FactSales** (grain: one row per order line item; primary key `OrderItemID`)

| Group | Columns |
|---|---|
| Keys | DateKey, CustomerKey, ProductKey, SellerKey, LocationKey, OrderID, OrderItemID |
| Measures | Quantity, UnitPrice, GrossAmount, DiscountAmount, NetAmount, CostAmount, ShippingFee, ShippingDays |
| Flags | IsCancelled, IsReturned |
| Returns | ReturnedAmount, ReturnDateKey, ReturnReason, ReturnStatus (valid returns only, aggregated per line) |
| Order attributes | OrderStatus, PaymentMethod, Channel |

**Dimensions**

| Dimension | Contents |
|---|---|
| DimDate | One row per day, 2024-01-01 to 2025-12-31: day, week, month, quarter, year, day name, weekend and holiday flags (Ramadan, Eid-ul-Fitr, Eid-ul-Adha, 14 August, 11.11, Black Friday) |
| DimCustomer | Deduplicated customers, contact details, registration date, birth year, gender, city details (SCD Type 1). A customer segment (RFM) is not stored yet |
| DimProduct | Name, standardized category and subcategory, brand, list price, cost price, weight |
| DimSeller | Name, join date, tier, rating, city details |
| DimLocation | City, province, region, population tier, coordinates |

Every dimension includes an **Unknown** member (key `-1`) for records without a valid reference (DimDate uses `DateKey = -1` for an unusable order date).

**How the open design points are handled**

- **OrderStatus, PaymentMethod, Channel** are stored directly on `FactSales` (no extra dimension, since the brief fixes the model at five dimensions). Orders can have several payment rows, so `PaymentMethod` is the method of one representative payment per order: a `Paid` payment first, then the cleaner's `payment_rank`.
- **ShippingFee** is one courier charge per order (the cleaned shipping table has one shipment per order). It is split equally across the order's lines, in `OrderItemID` order, with the rounding remainder placed on the last line, so the lines of an order always add up to exactly one fee and nothing is double counted. Orders with no shipment get 0.
- **Returns** are aggregated per order line from valid returns only (status Approved or Refunded): `ReturnedAmount` is the sum of refunds, `ReturnDateKey` is the earliest return date, and `ReturnReason` / `ReturnStatus` come from that earliest return.
- **Cancelled orders** stay in the fact with `IsCancelled = true`; metrics exclude them where the brief says so.

## Data Cleaning Rules

Every cleaning decision is implemented in code (`include/clean/`), logged with before-and-after counts, and counted per run in `data/processed/clean_stats.csv`. Records that cannot be repaired are written to `data/processed/rejects.csv` with a **reason code** and the original raw record, never silently deleted; each cleaner asserts `rows_in == rows_out + rejected`. Label variants live in `include/clean/mappings.py`; any spelling not listed becomes `Unknown` and is counted. All columns are read as text so that type conversion is an explicit, logged decision.

Counts below are for the provided dataset: "before" figures come from the raw profile (`docs/dq_log.csv`) and "after" figures from the cleaned output and warehouse snapshot in `data/export/`. The authoritative per-run numbers are in `clean_stats.csv` and `rejects.csv`, which are regenerated by the `clean` task.

| Issue | Rule applied | Rows before | Rows after | Rejected |
|---|---|---|---|---|
| Missing values | Decided per column; rows are kept, nothing is dropped. Optional text attributes stay null or become `Unknown` (brand, sub-category, return reason, gender, ship city, tier). Brand is filled from the product name when it matches a known brand. Missing cost and weight are borrowed from a merged duplicate product. Missing line discount is recomputed from the order's `SAVE<n>` code. Missing shipping fee gets the typical fee for an order of that value (flag `shipping_fee_missing` kept in staging). Missing shipped and delivered dates are left null, not invented. Examples of raw nulls: customer email 1,698, phone 3,599, birth year 4,600; product sub-category 485, cost price 170; shipping fee 9,145 | n/a | n/a | 0 |
| Exact duplicate rows | First copy kept, later identical copies rejected (`EXACT_DUPLICATE`). Orders 3,200 and payments 3,296; the other files have none. Duplicate ids with different content keep the first row (`DUPLICATE_ID`) | orders 163,200; payments 168,111 | orders 160,000; payments 164,815 (before later steps) | 6,496 |
| Duplicate customers / products | Merged under the lowest id as master, with `customer_map.csv` / `product_map.csv` so orders and lines are re-linked. Customers: same normalized name **and** (same email **or** same phone) **and** same birth year, linked transitively. Products: same normalized name (suffixes such as `- New`, `(2024)`, `Original` removed) **and** list prices within 5%. Never matched on name alone | customers 45,000; products 3,200 | customers 42,983; products 3,096 | customers 2,017 merged; products 104 merged |
| Inconsistent categories | 74 raw category spellings mapped to the 12 canonical categories (`CATEGORY` map). Same approach for order status (4 values: Delivered, Cancelled, Returned, In Transit; `Shipped` becomes In Transit), channel (Web, App, Mobile Web), payment method (`Debit/Credit Card` merge into Card), payment status, courier, delivery status, return status and reason, province, gender, seller tier | 74 category variants | 12 categories | 0 |
| Invalid dates | Three formats parsed (`YYYY-MM-DD`, `DD/MM/YYYY`, `Mon DD YYYY`); slash dates are day/month/year. Impossible dates become null. Valid order range is 1 Jan 2024 to 30 Jun 2025. An order date that is unparseable or out of range is repaired from the primary payment date, then the shipped date; if neither is usable the order is quarantined (`ORDER_DATE_UNREPAIRABLE`) and its lines, payments and shipments follow. Raw profile: 1,150 unparseable and 491 out-of-range order dates. Other dates are nulled, not dropped: delivered before shipped (1,269), return before its order, future registration or join date | orders 160,000 (after exact dedup) | orders 159,988 | 12 orders (lines, payments, shipments cascade) |
| Incorrect data types | Everything read as text, then converted: `Rs. 2,290` becomes 2290; `9,999,999` is a placeholder and treated as missing in price, discount, fee, order total, payment amount and list price; quantity words (`two`) become numbers and negative quantities are made positive (sign error, checked against order totals); quantity 0 or fractional is rejected (`INVALID_QUANTITY`); phone numbers normalized to `03xxxxxxxxx`; invalid emails nulled; negative order totals sign-corrected and zero totals set to missing | order_items 315,143 | order_items 315,109 | 34 lines |
| Outliers | Unit price compared with the product list price (normal lines sell at 0.9 to 1.1 times list): ratio about 100 is divided by 100; ratio about 0.0036 (US dollars) is multiplied by 280; anything else implausible falls back to the list price (`INVALID_PRICE` reject if no reference). Quantity placeholder 500 (641 lines) is solved from the order total, else set to 1. Line discount above gross (1,654) or off from the order's code is recomputed. Shipping fee above 5,000 or negative is nulled. Seller rating outside 0 to 5 nulled (11). Cost price at or below zero or above list price nulled (75 above list). Weight at or below zero nulled (10). Birth year outside 1930 to 2010 nulled. Coordinates outside Pakistan nulled | n/a | n/a | covered by the line counts above |
| Broken references | Rule of thumb: if the revenue can still be counted, map to the `Unknown` member; if the record cannot be attributed, quarantine it. Orders with a missing customer (330 in the raw profile) map to Unknown customer; order lines with a missing product (932) map to Unknown product; orders with no or invalid ship city (6,516) map to Unknown location. Returns whose order line does not exist are rejected (`ORPHAN_ORDER_ITEM`, 139 in the raw profile); lines, payments and shipments of quarantined orders are rejected (`ORPHAN_ORDER`). A second shipment for the same order is rejected (`DUPLICATE_ORDER_SHIPMENT`) | returns 16,048; shipping 151,228 | returns 15,908; shipping 151,223 | returns 140; shipping 5 |

Reconciliation after repair: 99.4% of orders match their `order_total`; the rest differ by a median of 44 PKR (see `include/clean/README.md`, which also lists every judgement call the team has to confirm).

## Business Metric Definitions

Definitions follow the competition brief.

| Metric | Definition |
|---|---|
| Gross sales | Sum of quantity x unit price over all order lines, before discounts and cancellations |
| Net Merchandise Value (NMV) | Sum of quantity x unit price - discount for non-cancelled lines (In Transit, non-cancelled orders count) |
| Net Revenue | NMV minus refunds from valid (non-Rejected) returns |
| Cost of Goods | cost_price x quantity on kept lines |
| Margin | Net revenue minus cost of goods on kept lines |
| Delivered lines | Non-cancelled lines whose order is not still In Transit |
| Kept lines | Non-cancelled lines without a valid return |
| Return Rate | Lines with a valid return / delivered lines |
| Cancellation Rate | Cancelled orders / all orders after duplicate removal |
| AOV | NMV / number of non-cancelled orders |
| Active customers | Distinct customers with at least one non-cancelled order |
| Units | Sum of quantity on non-cancelled lines |

A return is valid when its status is Approved or Refunded; Rejected (and any status that could not be mapped) is not valid.

**Python and SQL reconciliation** (`notebooks/metric_reconciliation.ipynb`, results in `docs/metric_reconciliation.csv`): the cleaned CSVs and the warehouse give identical results.

| Metric | Python | SQL |
|---|---|---|
| Total orders | 159,988 | 159,988 |
| NMV (non-cancelled) | 1,199,304,794 PKR | not recorded |
| Valid refunds | 58,033,099 PKR | 58,033,099 PKR |
| Net Revenue | 1,141,271,695 PKR | 1,141,271,695 PKR |
| Return Rate | 5.1483% (14,597 of 283,531 delivered lines) | 5.1483% |
| Shipping fee total | 81,388,942 PKR | 81,388,942 PKR |

Additional analytical metrics required by the brief: Customer Lifetime Value (observed), Repeat Purchase Rate, RFM Segmentation, Seller Quality Score and On-Time Delivery Rate.

> Pending (with the dashboard): these are not implemented in the repository yet. <!-- TODO (on hold): document RFM scoring, Seller Quality Score weights and the on-time delivery threshold, with the reasoning behind each. -->

## Power BI Dashboard

The dashboard will connect to the **warehouse tables**, not the raw CSVs. Target location: `powerbi/`.

| Page | Focus |
|---|---|
| Executive Overview | Net Revenue, Orders, AOV, Units, Return Rate, Cancellation Rate, Active Customers, month-over-month change |
| Time Analysis | Monthly and weekly trends, moving averages, seasonality, festival comparisons |
| Product & Category | Category revenue and margin, top and bottom products, sales versus return rates |
| Geography | City, province and region performance, location-tier comparison |
| Customer Analysis | New versus returning, RFM segments, retention or cohorts, top customers |
| Seller Performance | Rankings, revenue, return rates, delivery times, tier comparison |
| Returns & Cancellations | Rates by category, seller and region; return reasons and trends |

Interactivity: slicers (date, category, region, seller tier, customer segment), drill-through or drill-down, and tooltip or bookmark views.

> **Status:** dashboard not yet included in this repository.

## Design Decisions

- **Separate warehouse container.** The warehouse is its own Postgres service (host port 5433), apart from the Airflow metadata database. Analytics tables can be reset or rebuilt without touching Airflow's state, and BI tools connect to one clean database.
- **Cleaning in Python, before the database.** Every file is read as text and cleaned in code, so each rule is repeatable, logged and tested against counts. Nothing is edited by hand, in Excel, in the database or in Power Query.
- **Staging layer, then typed star schema.** Staging tables mirror the cleaned CSV headers as `TEXT`; only the dimensions and fact use typed columns, so type casts happen in one place (the SQL build scripts).
- **Idempotency by full rebuild.** `reset_database` empties staging and the fact and deletes all dimension rows except the Unknown members before each load. Dimensions and the fact are then rebuilt from the current cleaned CSVs (dimensions with upserts, the fact with truncate and insert). A full rebuild guarantees that customers or products merged or removed in a later cleaning run cannot linger in a dimension, and it is simple to reason about at this data size. `DimDate` is regenerated from a fixed calendar.
- **Returns keep the fact grain.** Returns are summed per `order_item_id` in a CTE and joined to the fact on that key, so an order line with several return rows still produces exactly one fact row. The `OrderItemID` primary key and the duplicate check in `quality_checks` enforce this.
- **Shipping fee allocation.** One courier charge per order is split equally across its lines with the remainder on the last line, so per-line fees always sum to the order's fee (checked per order in `quality_checks`).
- **Duplicate customers and products.** Matching uses several fields, never the name alone, and is transitive. The lowest id becomes the master and every other id is kept in a mapping table, so orders and lines still link to the master. The matching thresholds (price within 5%, birth-year rule) are judgement calls listed in `include/clean/README.md`.
- **SCD Type 1 for DimCustomer.** The source has no change history, so changed attributes simply overwrite the previous values (`ON CONFLICT ... DO UPDATE`).
- **Unknown members versus quarantine.** If a record's revenue can still be counted correctly, the broken reference is mapped to the Unknown member, so sales totals are preserved. If a record cannot be attributed (an order line or return pointing at a missing order, an order with no usable date), it is rejected with a reason code instead of guessed.
- **Order attributes on the fact.** The brief fixes five dimensions, so OrderStatus, PaymentMethod and Channel live on `FactSales` rather than in extra dimensions.
- **Zero-tolerance quality gates.** Any broken relationship, null key, empty dimension, duplicate line or shipping mismatch stops the run before anyone reads the warehouse.

## Known Limitations

- **Order dates are repaired heuristically.** Missing or out-of-range order dates are taken from the primary payment date, then the shipped date; this rule has not been validated against orders with a good date. 12 orders could not be repaired and are quarantined.
- **Imputed values.** About 9,477 missing or invalid shipping fees are filled with the typical fee for the order's value, and unknown quantities (placeholder 500) fall back to 1 when the order total cannot solve them. `shipping_fee_missing` marks the shipping fills in staging, but the flag is not carried into `FactSales`.
- **Residual duplicate customers.** A pair where only one record has a birth year is not merged by the current rule, so some duplicate customers may remain (candidates are listed in `docs/dq_review.csv`).
- **One payment method per order.** Some orders have several payment attempts or methods; the fact stores a single representative one, so payment-method analysis should be read with that in mind.
- **Festival dates are fixed calendar values** taken from the brief, not moon-sighting confirmations; the Black Friday flag also marks 28 Nov 2025, which is outside the data period.
- **Mapping and reject tables.** `customer_map.csv`, `product_map.csv` and `rejects.csv` are written as files in `data/processed/`; the warehouse has empty `rejects`, `customer_map` and `product_map` tables that the DAG does not populate.
- **No automated tests.** Quality is enforced by the pipeline checks and `verify_star_v2.sql`; the `tests/` folder mentioned in `include/clean/README.md` does not exist yet.
- **Unmapped labels** (new spellings) become `Unknown` and are counted rather than guessed.

## Deliverables Checklist

| # | Deliverable | Location |
|---|---|---|
| 1 | Airflow DAGs | `dags/nexusmart_pipeline.py` |
| 2 | Database schema and SQL scripts | `include/sql/` |
| 3 | Star schema diagram | 'docs/star_schema.png'|
| 4 | Power BI dashboard (.pbix) | '/powerbi/nexusmart.pbix' |
| 5 | Dashboard PDF export | (`powerbi/Nexus Mart.pbix`) |
| 6 | Executive Summary (2-3 page PDF) | (`docs/documentation`) |
| 7 | Source code | this repository |
| 8 | README | this file |
| 9 | Data Quality Report | Counts in [Data Cleaning Rules](#data-cleaning-rules); profiling outputs in `docs/dq_*.csv`; consolidated report pending |
