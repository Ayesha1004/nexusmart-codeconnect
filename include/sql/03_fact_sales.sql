-- 03_fact_sales.sql — Transaction grain: precisely ONE row per cleaned order_item_id.
-- Assumptions: valid returns are Refunded or Approved, never Rejected; first ranked
-- payment per order is used (prefer Paid and payment_rank); one shipping fee/order.
-- Orders with invalid dates are kept and use Unknown DateKey (-1).
BEGIN;
TRUNCATE TABLE "FactSales";
WITH payment_choice AS (
  SELECT order_id, payment_method FROM (
    SELECT p.order_id,p.payment_method,
      row_number() OVER(PARTITION BY p.order_id ORDER BY
        CASE WHEN p.payment_status='Paid' THEN 0 ELSE 1 END,
        NULLIF(p.payment_rank,'')::int NULLS LAST, p.payment_id) AS rn
    FROM stg_payments p
  ) x WHERE rn=1
), return_agg AS (
  SELECT order_item_id, SUM(COALESCE(NULLIF(refund_amount,'')::numeric,0)) AS refunds,
    MIN(NULLIF(return_date,'')::date) AS first_return_date,
    (array_agg(return_reason ORDER BY return_date,return_id))[1] AS return_reason,
    (array_agg(return_status ORDER BY return_date,return_id))[1] AS return_status
  FROM stg_returns
  WHERE return_status IN ('Approved','Refunded')
  GROUP BY order_item_id
), shipping_choice AS (
  SELECT order_id, MAX(COALESCE(NULLIF(shipping_fee,'')::numeric,0)) AS total_fee,
    MIN(NULLIF(shipped_date,'')::date) AS shipped_date,
    MAX(NULLIF(delivered_date,'')::date) AS delivered_date
  FROM stg_shipping GROUP BY order_id
), base AS (
 SELECT i.order_item_id,i.order_id,
   COALESCE(d."DateKey",-1) AS date_key,
   CASE WHEN r.first_return_date IS NULL THEN NULL ELSE COALESCE(rd."DateKey",-1) END AS return_date_key,
   COALESCE(c."CustomerKey",-1) AS customer_key,
   COALESCE(p."ProductKey",-1) AS product_key,
   COALESCE(s."SellerKey",-1) AS seller_key,
   COALESCE(l."LocationKey",-1) AS location_key,
   COALESCE(NULLIF(i.quantity,'')::numeric,0) AS quantity,
   COALESCE(NULLIF(i.unit_price,'')::numeric,0) AS unit_price,
   COALESCE(NULLIF(i.discount_amount,'')::numeric,0) AS discount_amount,
   COALESCE(p."CostPrice",0) AS cost_price,
   COALESCE(ship.total_fee,0) AS order_shipping_fee,
   CASE WHEN NULLIF(ship.delivered_date::text,'') IS NOT NULL
             AND ship.shipped_date IS NOT NULL
        THEN ship.delivered_date-ship.shipped_date ELSE NULL END AS shipping_days,
   COALESCE(o.order_status='Cancelled',false) AS is_cancelled,
   r.order_item_id IS NOT NULL AS is_returned,
   COALESCE(r.refunds,0) AS returned_amount,
   r.return_reason,r.return_status,o.order_status,pay.payment_method,o.channel,
   row_number() OVER (PARTITION BY i.order_id ORDER BY i.order_item_id) AS line_no,
   count(*) OVER (PARTITION BY i.order_id) AS line_count
 FROM stg_order_items i
 JOIN stg_orders o ON o.order_id=i.order_id
 LEFT JOIN "DimDate" d ON d."FullDate"=NULLIF(o.order_date,'')::date
 LEFT JOIN "DimCustomer" c ON c."CustomerID"=o.customer_id
 LEFT JOIN "DimProduct" p ON p."ProductID"=i.product_id
 LEFT JOIN "DimSeller" s ON s."SellerID"=i.seller_id
 LEFT JOIN "DimLocation" l ON l."CityID"=o.ship_city_id
 LEFT JOIN return_agg r ON r.order_item_id=i.order_item_id
 LEFT JOIN "DimDate" rd ON rd."FullDate"=r.first_return_date
 LEFT JOIN payment_choice pay ON pay.order_id=o.order_id
 LEFT JOIN shipping_choice ship ON ship.order_id=o.order_id
)
INSERT INTO "FactSales" ("OrderItemID","OrderID","DateKey","ReturnDateKey","CustomerKey","ProductKey",
 "SellerKey","LocationKey","Quantity","UnitPrice","GrossAmount","DiscountAmount","NetAmount",
 "CostAmount","ShippingFee","ShippingDays","IsCancelled","IsReturned","ReturnedAmount",
 "ReturnReason","ReturnStatus","OrderStatus","PaymentMethod","Channel")
SELECT order_item_id,order_id,date_key,return_date_key,customer_key,product_key,seller_key,location_key,
 quantity,unit_price,ROUND(quantity*unit_price,2),discount_amount,
 ROUND(quantity*unit_price-discount_amount,2),ROUND(quantity*cost_price,2),
 CASE WHEN line_no<line_count THEN ROUND(order_shipping_fee/line_count,2)
      ELSE order_shipping_fee-ROUND(order_shipping_fee/line_count,2)*(line_count-1) END,
 shipping_days,is_cancelled,is_returned,returned_amount,return_reason,return_status,
 order_status,payment_method,channel
FROM base;
COMMIT;
