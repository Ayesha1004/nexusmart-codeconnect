-- 00_reset.sql — run BEFORE loading the cleaned CSVs into staging, on every pipeline run.
-- Makes the whole load repeatable: staging, fact and dimensions are rebuilt from the current cleaned CSVs,
-- so merged/removed customers or products from an earlier run cannot linger in the dimensions.
-- The -1 'Unknown' members and DimDate are kept.
BEGIN;
TRUNCATE stg_locations, stg_sellers, stg_products, stg_customers, stg_orders,
         stg_order_items, stg_payments, stg_shipping, stg_returns,
         rejects, customer_map, product_map;
TRUNCATE "FactSales";
DELETE FROM "DimCustomer" WHERE "CustomerKey" <> -1;
DELETE FROM "DimProduct"  WHERE "ProductKey"  <> -1;
DELETE FROM "DimSeller"   WHERE "SellerKey"   <> -1;
DELETE FROM "DimLocation" WHERE "LocationKey" <> -1;
COMMIT;
