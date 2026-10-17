-- 02_dimensions.sql — Run AFTER the cleaned CSVs have been loaded into staging.
-- SCD Type 1: changes overwrite previous dimension attributes.
BEGIN;
INSERT INTO "DimDate" ("DateKey","FullDate","Day","Week","Month","Quarter","Year","DayName",
 "IsWeekend","IsHoliday","IsRamadan","IsEidUlFitr","IsEidUlAdha","Is14August","Is1111","IsBlackFriday")
VALUES (-1,NULL,NULL,NULL,NULL,NULL,NULL,'Unknown',FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE)
ON CONFLICT ("DateKey") DO NOTHING;
-- Festival dates listed here are provisional calendar approximations; confirm Pakistan moon sightings.
WITH dates AS (
 SELECT d::date AS dt FROM generate_series('2024-01-01'::date, '2025-12-31'::date, interval '1 day') AS s(d)
), flags AS (
 SELECT dt,
 (dt BETWEEN '2024-03-11' AND '2024-04-09' OR dt BETWEEN '2025-03-01' AND '2025-03-30') AS ramadan,
 (dt BETWEEN '2024-04-10' AND '2024-04-12' OR dt BETWEEN '2025-03-31' AND '2025-04-02') AS fitr,
 (dt BETWEEN '2024-06-17' AND '2024-06-19' OR dt BETWEEN '2025-06-07' AND '2025-06-09') AS adha
 FROM dates
)
INSERT INTO "DimDate"
SELECT to_char(dt,'YYYYMMDD')::integer,dt,extract(day from dt)::int,
 extract(week from dt)::int,extract(month from dt)::int,extract(quarter from dt)::int,
 extract(year from dt)::int,trim(to_char(dt,'Day')),
 extract(isodow from dt) IN (6,7),
 fitr OR adha OR (extract(month from dt)=8 AND extract(day from dt)=14),
 ramadan,fitr,adha,
 (extract(month from dt)=8 AND extract(day from dt)=14),
 (extract(month from dt)=11 AND extract(day from dt)=11),
 (dt='2024-11-29'::date OR dt='2025-11-28'::date)
FROM flags ON CONFLICT ("DateKey") DO UPDATE SET
 "IsHoliday"=EXCLUDED."IsHoliday", "IsRamadan"=EXCLUDED."IsRamadan",
 "IsEidUlFitr"=EXCLUDED."IsEidUlFitr", "IsEidUlAdha"=EXCLUDED."IsEidUlAdha";

INSERT INTO "DimLocation"("LocationKey","CityID","City","Province","Region","PopulationTier")
VALUES(-1,'UNKNOWN','Unknown','Unknown','Unknown','Unknown')
ON CONFLICT ("LocationKey") DO NOTHING;
INSERT INTO "DimLocation"("CityID","City","Province","Region","PopulationTier","Latitude","Longitude")
SELECT city_id,city,province,region,population_tier,
 NULLIF(latitude,'')::numeric,NULLIF(longitude,'')::numeric
FROM stg_locations WHERE NULLIF(city_id,'') IS NOT NULL
ON CONFLICT ("CityID") DO UPDATE SET
 "City"=EXCLUDED."City", "Province"=EXCLUDED."Province", "Region"=EXCLUDED."Region",
 "PopulationTier"=EXCLUDED."PopulationTier", "Latitude"=EXCLUDED."Latitude", "Longitude"=EXCLUDED."Longitude";

INSERT INTO "DimCustomer"("CustomerKey","CustomerID","FullName") VALUES(-1,'UNKNOWN','Unknown')
ON CONFLICT ("CustomerKey") DO NOTHING;
INSERT INTO "DimCustomer" ("CustomerID","FullName","Email","Phone","Gender","BirthYear",
 "RegistrationDate","CityID","City","Province","Region")
SELECT c.customer_id,c.full_name,c.email,c.phone,c.gender,NULLIF(c.birth_year,'')::int,
 NULLIF(c.registration_date,'')::date,c.city_id,l.city,l.province,l.region
FROM stg_customers c LEFT JOIN stg_locations l ON c.city_id=l.city_id
WHERE NULLIF(c.customer_id,'') IS NOT NULL
ON CONFLICT ("CustomerID") DO UPDATE SET
 "FullName"=EXCLUDED."FullName","Email"=EXCLUDED."Email","Phone"=EXCLUDED."Phone",
 "Gender"=EXCLUDED."Gender","BirthYear"=EXCLUDED."BirthYear",
 "RegistrationDate"=EXCLUDED."RegistrationDate","CityID"=EXCLUDED."CityID",
 "City"=EXCLUDED."City","Province"=EXCLUDED."Province","Region"=EXCLUDED."Region";

INSERT INTO "DimProduct"("ProductKey","ProductID","ProductName") VALUES(-1,'UNKNOWN','Unknown')
ON CONFLICT ("ProductKey") DO NOTHING;
INSERT INTO "DimProduct"("ProductID","ProductName","Category","SubCategory","Brand","ListPrice","CostPrice","WeightKg")
SELECT product_id,product_name,category,sub_category,brand,
 NULLIF(list_price,'')::numeric,NULLIF(cost_price,'')::numeric,NULLIF(weight_kg,'')::numeric
FROM stg_products WHERE NULLIF(product_id,'') IS NOT NULL
ON CONFLICT ("ProductID") DO UPDATE SET
 "ProductName"=EXCLUDED."ProductName","Category"=EXCLUDED."Category",
 "SubCategory"=EXCLUDED."SubCategory","Brand"=EXCLUDED."Brand",
 "ListPrice"=EXCLUDED."ListPrice","CostPrice"=EXCLUDED."CostPrice","WeightKg"=EXCLUDED."WeightKg";

INSERT INTO "DimSeller"("SellerKey","SellerID","SellerName") VALUES(-1,'UNKNOWN','Unknown')
ON CONFLICT ("SellerKey") DO NOTHING;
INSERT INTO "DimSeller"("SellerID","SellerName","JoinDate","SellerTier","Rating","CityID","City","Province","Region")
SELECT s.seller_id,s.seller_name,NULLIF(s.join_date,'')::date,s.seller_tier,
 NULLIF(s.rating,'')::numeric,s.city_id,l.city,l.province,l.region
FROM stg_sellers s LEFT JOIN stg_locations l ON s.city_id=l.city_id
WHERE NULLIF(s.seller_id,'') IS NOT NULL
ON CONFLICT ("SellerID") DO UPDATE SET
 "SellerName"=EXCLUDED."SellerName","JoinDate"=EXCLUDED."JoinDate",
 "SellerTier"=EXCLUDED."SellerTier","Rating"=EXCLUDED."Rating","CityID"=EXCLUDED."CityID",
 "City"=EXCLUDED."City","Province"=EXCLUDED."Province","Region"=EXCLUDED."Region";
COMMIT;
