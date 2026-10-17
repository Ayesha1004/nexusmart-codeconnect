-- verify_star_v2.sql — run after 03_fact_sales.sql. Every row has a status: PASS / FAIL / REVIEW.
-- FAIL = the build is wrong. REVIEW = a number a human must look at and explain.
-- (FK checks are not repeated: the FactSales foreign keys already make them impossible.)
WITH checks AS (
  SELECT 1 AS n, 'Fact rows = staging order items' AS check_name,
         (SELECT COUNT(*) FROM "FactSales") - (SELECT COUNT(*) FROM stg_order_items) AS value, 'FAIL' AS if_nonzero
  UNION ALL SELECT 2, 'Net amount: fact minus staging (qty*price-discount)',
         ROUND((SELECT COALESCE(SUM("NetAmount"),0) FROM "FactSales")
             - (SELECT COALESCE(SUM(quantity::numeric*unit_price::numeric-COALESCE(NULLIF(discount_amount,'')::numeric,0)),0) FROM stg_order_items),0), 'FAIL'
  UNION ALL SELECT 3, 'Valid-returned lines: fact minus staging',
         (SELECT COUNT(*) FROM "FactSales" WHERE "IsReturned")
       - (SELECT COUNT(DISTINCT order_item_id) FROM stg_returns r WHERE return_status IN ('Approved','Refunded')
            AND EXISTS (SELECT 1 FROM stg_order_items i WHERE i.order_item_id=r.order_item_id)), 'FAIL'
  UNION ALL SELECT 4, 'Refund amount: fact minus staging valid returns',
         ROUND((SELECT COALESCE(SUM("ReturnedAmount"),0) FROM "FactSales")
             - (SELECT COALESCE(SUM(NULLIF(refund_amount,'')::numeric),0) FROM stg_returns r WHERE return_status IN ('Approved','Refunded')
                  AND EXISTS (SELECT 1 FROM stg_order_items i WHERE i.order_item_id=r.order_item_id)),0), 'FAIL'
  UNION ALL SELECT 5, 'Shipping fee: fact minus staging (per order, once)',
         ROUND((SELECT COALESCE(SUM("ShippingFee"),0) FROM "FactSales")
             - (SELECT COALESCE(SUM(f),0) FROM (SELECT MAX(COALESCE(NULLIF(shipping_fee,'')::numeric,0)) f FROM stg_shipping
                  WHERE order_id IN (SELECT order_id FROM stg_order_items) GROUP BY order_id) x),2), 'FAIL'
  UNION ALL SELECT 6, 'IsCancelled disagrees with OrderStatus',
         (SELECT COUNT(*) FROM "FactSales" WHERE "IsCancelled" <> ("OrderStatus"='Cancelled')), 'FAIL'
  UNION ALL SELECT 7, 'Lines with Unknown order date (DateKey = -1)', (SELECT COUNT(*) FROM "FactSales" WHERE "DateKey"=-1), 'FAIL'
  UNION ALL SELECT 8, 'Lines dated outside 2024-01-01..2025-06-30',
         (SELECT COUNT(*) FROM "FactSales" f JOIN "DimDate" d USING("DateKey") WHERE d."FullDate" NOT BETWEEN '2024-01-01' AND '2025-06-30'), 'FAIL'
  UNION ALL SELECT 9, 'DimCustomer rows not in staging (stale)',
         (SELECT COUNT(*) FROM "DimCustomer" WHERE "CustomerKey"<>-1 AND "CustomerID" NOT IN (SELECT customer_id FROM stg_customers)), 'FAIL'
  UNION ALL SELECT 10, 'DimProduct rows not in staging (stale)',
         (SELECT COUNT(*) FROM "DimProduct" WHERE "ProductKey"<>-1 AND "ProductID" NOT IN (SELECT product_id FROM stg_products)), 'FAIL'
  -- the next ones are not necessarily wrong, but someone must be able to explain the number
  UNION ALL SELECT 11, 'Lines on Unknown customer',  (SELECT COUNT(*) FROM "FactSales" WHERE "CustomerKey"=-1), 'REVIEW'
  UNION ALL SELECT 12, 'Lines on Unknown product',   (SELECT COUNT(*) FROM "FactSales" WHERE "ProductKey"=-1), 'REVIEW'
  UNION ALL SELECT 13, 'Lines on Unknown seller',    (SELECT COUNT(*) FROM "FactSales" WHERE "SellerKey"=-1), 'REVIEW'
  UNION ALL SELECT 14, 'Lines on Unknown ship location', (SELECT COUNT(*) FROM "FactSales" WHERE "LocationKey"=-1), 'REVIEW'
  UNION ALL SELECT 15, 'Valid returns on CANCELLED orders (should a cancelled order be returnable?)',
         (SELECT COUNT(*) FROM "FactSales" WHERE "IsReturned" AND "IsCancelled"), 'REVIEW'
  UNION ALL SELECT 16, 'Orders whose shipping fee was missing (loaded as 0)',
         (SELECT COUNT(*) FROM stg_shipping WHERE shipping_fee_missing='True'), 'REVIEW'
  UNION ALL SELECT 17, 'Orders where sum of line NetAmount differs from order_total by > 1',
         (SELECT COUNT(*) FROM (SELECT o.order_id FROM stg_orders o JOIN "FactSales" f ON f."OrderID"=o.order_id
            WHERE NULLIF(o.order_total,'') IS NOT NULL GROUP BY o.order_id, o.order_total
            HAVING ABS(SUM(f."NetAmount") - o.order_total::numeric) > 1) x), 'REVIEW'
)
SELECT n, check_name, value,
       CASE WHEN value = 0 THEN 'PASS' ELSE if_nonzero END AS status
FROM checks ORDER BY n;
