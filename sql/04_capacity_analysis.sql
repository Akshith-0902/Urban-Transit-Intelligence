-- =============================================================================
-- 04_capacity_analysis.sql
-- Purpose: Occupancy rate, capacity utilization, overcrowding vs underutilized routes
-- Phase: 3 (SQL Analytics)
-- Status: DONE
--
-- Business questions answered (docs/business_requirements.md > Capacity Utilization):
--   - Which routes are overcrowded vs. underutilized?
--   - What is average/peak occupancy, and how does it change through the day?
--   - Which routes show the largest supply-demand mismatch? (headline ranking
--     here; the cross-cutting reallocation view lives in 06_advanced_analysis.sql)
--
-- Convention: occupancy_ratio = passenger_count (onboard load at a stop) /
-- bus capacity for that trip. Peak windows (07:00-10:00, 17:00-20:00) match
-- docs/assumptions.md. This mirrors the plausibility check already run in
-- sql/01_data_validation.sql section 5, but here the goal is business
-- interpretation (route ranking) rather than data-quality flagging.
--
-- Run: psql -d urban_transit_intelligence -f sql/04_capacity_analysis.sql
-- =============================================================================


-- =============================================================================
-- 1. NETWORK-WIDE OCCUPANCY
-- =============================================================================
\echo '--- 1.1 Network-wide occupancy ratio, peak vs off-peak ---'
SELECT CASE WHEN pc."timestamp"::time BETWEEN TIME '07:00' AND TIME '10:00'
             OR pc."timestamp"::time BETWEEN TIME '17:00' AND TIME '20:00'
            THEN 'Peak' ELSE 'Off-peak' END AS period,
       ROUND(AVG(pc.passenger_count::numeric / b.capacity), 2) AS mean_occupancy_ratio,
       ROUND(MAX(pc.passenger_count::numeric / b.capacity), 2) AS max_occupancy_ratio,
       COUNT(*) FILTER (WHERE pc.passenger_count::numeric / b.capacity > 1.0) AS records_over_capacity
FROM passenger_counts pc
JOIN trips t ON t.trip_id = pc.trip_id
JOIN buses b ON b.bus_id = t.bus_id
GROUP BY 1
ORDER BY 1;

\echo '--- 1.2 Occupancy ratio by route_type and period ---'
SELECT r.route_type,
       CASE WHEN pc."timestamp"::time BETWEEN TIME '07:00' AND TIME '10:00'
             OR pc."timestamp"::time BETWEEN TIME '17:00' AND TIME '20:00'
            THEN 'Peak' ELSE 'Off-peak' END AS period,
       ROUND(AVG(pc.passenger_count::numeric / b.capacity), 2) AS mean_occupancy_ratio,
       ROUND(MAX(pc.passenger_count::numeric / b.capacity), 2) AS max_occupancy_ratio,
       COUNT(*) FILTER (WHERE pc.passenger_count::numeric / b.capacity > 1.0) AS records_over_capacity
FROM passenger_counts pc
JOIN trips t  ON t.trip_id = pc.trip_id
JOIN routes r ON r.route_id = t.route_id
JOIN buses b  ON b.bus_id = t.bus_id
GROUP BY r.route_type, 2
ORDER BY r.route_type, period;


-- =============================================================================
-- 2. OVERCROWDED ROUTES
-- =============================================================================
\echo '--- 2.1 Top 15 routes by peak-hour occupancy ratio (overcrowding candidates) ---'
SELECT r.route_id, r.route_number, r.route_name, r.route_type,
       ROUND(AVG(pc.passenger_count::numeric / b.capacity), 2) AS avg_peak_occupancy,
       ROUND(MAX(pc.passenger_count::numeric / b.capacity), 2) AS max_peak_occupancy,
       COUNT(*) FILTER (WHERE pc.passenger_count::numeric / b.capacity > 1.0) AS peak_records_over_capacity
FROM passenger_counts pc
JOIN trips t  ON t.trip_id = pc.trip_id
JOIN routes r ON r.route_id = t.route_id
JOIN buses b  ON b.bus_id = t.bus_id
WHERE pc."timestamp"::time BETWEEN TIME '07:00' AND TIME '10:00'
   OR pc."timestamp"::time BETWEEN TIME '17:00' AND TIME '20:00'
GROUP BY r.route_id, r.route_number, r.route_name, r.route_type
ORDER BY avg_peak_occupancy DESC
LIMIT 15;

\echo '--- 2.2 Stop-level severe overcrowding: records above 150% of capacity, by route ---'
SELECT r.route_id, r.route_number, r.route_type,
       COUNT(*) AS records_over_150pct
FROM passenger_counts pc
JOIN trips t  ON t.trip_id = pc.trip_id
JOIN routes r ON r.route_id = t.route_id
JOIN buses b  ON b.bus_id = t.bus_id
WHERE pc.passenger_count::numeric / b.capacity > 1.5
GROUP BY r.route_id, r.route_number, r.route_type
ORDER BY records_over_150pct DESC
LIMIT 15;


-- =============================================================================
-- 3. UNDERUTILIZED ROUTES (release-capacity candidates)
-- =============================================================================
\echo '--- 3.1 Routes with the lowest overall mean occupancy (candidates to release capacity) ---'
SELECT r.route_id, r.route_number, r.route_name, r.route_type,
       ROUND(AVG(pc.passenger_count::numeric / b.capacity), 2) AS mean_occupancy_ratio,
       ROUND(MAX(pc.passenger_count::numeric / b.capacity), 2) AS max_occupancy_ratio,
       COUNT(DISTINCT t.bus_id)                                  AS buses_used
FROM passenger_counts pc
JOIN trips t  ON t.trip_id = pc.trip_id
JOIN routes r ON r.route_id = t.route_id
JOIN buses b  ON b.bus_id = t.bus_id
GROUP BY r.route_id, r.route_number, r.route_name, r.route_type
ORDER BY mean_occupancy_ratio ASC
LIMIT 15;

\echo '--- 3.2 Underutilized even at peak: routes whose PEAK occupancy never exceeds 40% ---'
SELECT r.route_id, r.route_number, r.route_name, r.route_type,
       ROUND(AVG(pc.passenger_count::numeric / b.capacity), 2) AS avg_peak_occupancy,
       ROUND(MAX(pc.passenger_count::numeric / b.capacity), 2) AS max_peak_occupancy
FROM passenger_counts pc
JOIN trips t  ON t.trip_id = pc.trip_id
JOIN routes r ON r.route_id = t.route_id
JOIN buses b  ON b.bus_id = t.bus_id
WHERE pc."timestamp"::time BETWEEN TIME '07:00' AND TIME '10:00'
   OR pc."timestamp"::time BETWEEN TIME '17:00' AND TIME '20:00'
GROUP BY r.route_id, r.route_number, r.route_name, r.route_type
HAVING MAX(pc.passenger_count::numeric / b.capacity) < 0.4
ORDER BY avg_peak_occupancy ASC;


-- =============================================================================
-- 4. OCCUPANCY THROUGH THE DAY (hourly granularity, network-wide)
-- =============================================================================
\echo '--- 4.1 Mean occupancy ratio by hour of day ---'
SELECT EXTRACT(HOUR FROM pc."timestamp")::int AS hour_of_day,
       ROUND(AVG(pc.passenger_count::numeric / b.capacity), 2) AS mean_occupancy_ratio,
       ROUND(MAX(pc.passenger_count::numeric / b.capacity), 2) AS max_occupancy_ratio
FROM passenger_counts pc
JOIN trips t ON t.trip_id = pc.trip_id
JOIN buses b ON b.bus_id = t.bus_id
GROUP BY 1
ORDER BY 1;

\echo '--- 4.2 Mean occupancy ratio by hour of day, Ordinary routes only (the most overcrowded tier) ---'
SELECT EXTRACT(HOUR FROM pc."timestamp")::int AS hour_of_day,
       ROUND(AVG(pc.passenger_count::numeric / b.capacity), 2) AS mean_occupancy_ratio
FROM passenger_counts pc
JOIN trips t  ON t.trip_id = pc.trip_id
JOIN routes r ON r.route_id = t.route_id
JOIN buses b  ON b.bus_id = t.bus_id
WHERE r.route_type = 'Ordinary'
GROUP BY 1
ORDER BY 1;


-- =============================================================================
-- 5. BUS-TYPE VIEW: does bus_type / capacity size relate to crowding?
-- =============================================================================
\echo '--- 5.1 Occupancy ratio by bus_type ---'
SELECT b.bus_type,
       ROUND(AVG(b.capacity), 0)                                AS avg_capacity,
       ROUND(AVG(pc.passenger_count::numeric / b.capacity), 2)  AS mean_occupancy_ratio,
       ROUND(MAX(pc.passenger_count::numeric / b.capacity), 2)  AS max_occupancy_ratio
FROM passenger_counts pc
JOIN trips t ON t.trip_id = pc.trip_id
JOIN buses b ON b.bus_id = t.bus_id
GROUP BY b.bus_type
ORDER BY mean_occupancy_ratio DESC;


-- =============================================================================
-- 6. SUPPLY-DEMAND MISMATCH (headline ranking)
--    "Mismatch score" here = peak occupancy ratio - mean occupancy ratio.
--    A large positive value means demand is heavily peak-loaded relative to
--    the route's own average — i.e. the route needs peak-only extra
--    frequency, not a bigger fleet all day. A full reallocation-candidate
--    pairing (overcrowded routes vs. release-capacity routes) is built in
--    06_advanced_analysis.sql.
-- =============================================================================
\echo '--- 6.1 Routes ranked by peak-vs-average occupancy gap ("peakiness") ---'
WITH per_route AS (
    SELECT r.route_id, r.route_number, r.route_type,
           AVG(pc.passenger_count::numeric / b.capacity) FILTER (
               WHERE pc."timestamp"::time BETWEEN TIME '07:00' AND TIME '10:00'
                  OR pc."timestamp"::time BETWEEN TIME '17:00' AND TIME '20:00'
           ) AS avg_peak_occupancy,
           AVG(pc.passenger_count::numeric / b.capacity) AS avg_overall_occupancy
    FROM passenger_counts pc
    JOIN trips t  ON t.trip_id = pc.trip_id
    JOIN routes r ON r.route_id = t.route_id
    JOIN buses b  ON b.bus_id = t.bus_id
    GROUP BY r.route_id, r.route_number, r.route_type
)
SELECT route_id, route_number, route_type,
       ROUND(avg_peak_occupancy, 2)    AS avg_peak_occupancy,
       ROUND(avg_overall_occupancy, 2) AS avg_overall_occupancy,
       ROUND(avg_peak_occupancy - avg_overall_occupancy, 2) AS peakiness_gap
FROM per_route
WHERE avg_peak_occupancy IS NOT NULL  -- excludes Night Service: no trips fall in the 07-10/17-20 peak windows
ORDER BY peakiness_gap DESC
LIMIT 15;
