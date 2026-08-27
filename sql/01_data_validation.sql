-- =============================================================================
-- 01_data_validation.sql
-- Purpose: Data quality checks — completeness, validity, consistency, uniqueness
-- Phase: 2 (Data Cleaning & Validation)
-- Status: DONE
--
-- Design note: routes/stops/route_stops/buses/trips/passenger_counts already
-- carry NOT NULL, CHECK, PRIMARY KEY, and FOREIGN KEY constraints in
-- 00_schema.sql. That means the classic completeness / validity / uniqueness
-- checks below CANNOT return violations on this database — Postgres would
-- have rejected the offending row at insert time. They're kept anyway (each
-- marked "schema-enforced, expect 0") so this file is a genuine, runnable
-- audit trail, not an assumption. The real findings-generating work lives in
-- section 4 (Consistency, cross-row) and section 5 (Plausibility) — logic
-- the schema cannot express in a single CHECK constraint.
--
-- Run: psql -d urban_transit_intelligence -f sql/01_data_validation.sql
-- =============================================================================


-- =============================================================================
-- 0. BASELINE ROW COUNTS
-- =============================================================================
\echo '--- 0. Baseline row counts ---'
SELECT 'routes' AS table_name, COUNT(*) AS row_count FROM routes
UNION ALL SELECT 'stops', COUNT(*) FROM stops
UNION ALL SELECT 'route_stops', COUNT(*) FROM route_stops
UNION ALL SELECT 'buses', COUNT(*) FROM buses
UNION ALL SELECT 'trips', COUNT(*) FROM trips
UNION ALL SELECT 'passenger_counts', COUNT(*) FROM passenger_counts
ORDER BY table_name;


-- =============================================================================
-- 1. COMPLETENESS  (schema-enforced via NOT NULL — expect 0 every time)
-- =============================================================================
\echo '--- 1.1 NULLs in required route fields ---'
SELECT COUNT(*) AS violations FROM routes
WHERE route_number IS NULL OR route_name IS NULL OR route_type IS NULL
   OR origin IS NULL OR destination IS NULL OR total_distance_km IS NULL;

\echo '--- 1.2 NULLs in trips ---'
SELECT COUNT(*) AS violations FROM trips
WHERE route_id IS NULL OR bus_id IS NULL OR service_date IS NULL
   OR scheduled_departure IS NULL OR actual_departure IS NULL
   OR scheduled_arrival IS NULL OR actual_arrival IS NULL;

\echo '--- 1.3 NULLs in passenger_counts ---'
SELECT COUNT(*) AS violations FROM passenger_counts
WHERE trip_id IS NULL OR stop_id IS NULL OR "timestamp" IS NULL
   OR boardings IS NULL OR alightings IS NULL OR passenger_count IS NULL;


-- =============================================================================
-- 2. VALIDITY  (schema-enforced via CHECK — expect 0 every time)
-- =============================================================================
\echo '--- 2.1 Negative/zero values guarded by CHECK constraints ---'
SELECT 'passenger_counts.boardings<0'        AS rule, COUNT(*) FROM passenger_counts WHERE boardings < 0
UNION ALL SELECT 'passenger_counts.alightings<0', COUNT(*) FROM passenger_counts WHERE alightings < 0
UNION ALL SELECT 'passenger_counts.passenger_count<0', COUNT(*) FROM passenger_counts WHERE passenger_count < 0
UNION ALL SELECT 'buses.capacity<=0', COUNT(*) FROM buses WHERE capacity <= 0
UNION ALL SELECT 'routes.total_distance_km<=0', COUNT(*) FROM routes WHERE total_distance_km <= 0
UNION ALL SELECT 'route_stops.stop_sequence<=0', COUNT(*) FROM route_stops WHERE stop_sequence <= 0;

\echo '--- 2.2 Stop coordinates outside the Chennai bounding box ---'
SELECT COUNT(*) AS violations FROM stops
WHERE NOT (latitude BETWEEN 12.6 AND 13.3 AND longitude BETWEEN 79.9 AND 80.4);

\echo '--- 2.3 Trip arrival earlier than departure ---'
SELECT COUNT(*) AS violations FROM trips
WHERE actual_arrival < actual_departure OR scheduled_arrival < scheduled_departure;


-- =============================================================================
-- 3. UNIQUENESS  (schema-enforced via PRIMARY KEY / UNIQUE — expect 0 every time)
-- =============================================================================
\echo '--- 3.1 Duplicate trip_id ---'
SELECT trip_id, COUNT(*) FROM trips GROUP BY trip_id HAVING COUNT(*) > 1;

\echo '--- 3.2 Duplicate (route_id, stop_id) pairs in route_stops ---'
SELECT route_id, stop_id, COUNT(*) FROM route_stops
GROUP BY route_id, stop_id HAVING COUNT(*) > 1;

\echo '--- 3.3 Duplicate route_number mapped to more than one route_id (business key, not a schema PK) ---'
SELECT route_number, COUNT(DISTINCT route_id) AS distinct_route_ids
FROM routes GROUP BY route_number HAVING COUNT(DISTINCT route_id) > 1;


-- =============================================================================
-- 4. CONSISTENCY (cross-row) — NOT schema-enforced. Findings expected here.
-- =============================================================================
\echo '--- 4.1 Orphans (redundant with FKs on this DB, but the check that matters against a raw CSV export) ---'
SELECT 'route_stops->routes' AS check_name, COUNT(*) AS violations
FROM route_stops rs LEFT JOIN routes r ON r.route_id = rs.route_id WHERE r.route_id IS NULL
UNION ALL
SELECT 'route_stops->stops', COUNT(*)
FROM route_stops rs LEFT JOIN stops s ON s.stop_id = rs.stop_id WHERE s.stop_id IS NULL
UNION ALL
SELECT 'trips->buses', COUNT(*)
FROM trips t LEFT JOIN buses b ON b.bus_id = t.bus_id WHERE b.bus_id IS NULL
UNION ALL
SELECT 'trips->routes', COUNT(*)
FROM trips t LEFT JOIN routes r ON r.route_id = t.route_id WHERE r.route_id IS NULL
UNION ALL
SELECT 'passenger_counts->trips', COUNT(*)
FROM passenger_counts pc LEFT JOIN trips t ON t.trip_id = pc.trip_id WHERE t.trip_id IS NULL;

\echo '--- 4.2 Bus double-booking: same bus on two overlapping trips the same day ---'
SELECT t1.bus_id, t1.trip_id AS trip_a, t2.trip_id AS trip_b,
       t1.actual_departure AS a_dep, t1.actual_arrival AS a_arr,
       t2.actual_departure AS b_dep, t2.actual_arrival AS b_arr
FROM trips t1
JOIN trips t2
  ON t1.bus_id = t2.bus_id
 AND t1.service_date = t2.service_date
 AND t1.trip_id < t2.trip_id
WHERE t1.actual_departure < t2.actual_arrival
  AND t2.actual_departure < t1.actual_arrival
ORDER BY t1.bus_id, t1.actual_departure;

\echo '--- 4.3 route_stops sequence gaps: stop_sequence not contiguous per route ---'
SELECT route_id,
       MIN(stop_sequence) AS min_seq,
       MAX(stop_sequence) AS max_seq,
       COUNT(*)           AS actual_count,
       (MAX(stop_sequence) - MIN(stop_sequence) + 1) AS expected_count_if_contiguous
FROM route_stops
GROUP BY route_id
HAVING COUNT(*) <> (MAX(stop_sequence) - MIN(stop_sequence) + 1)
ORDER BY route_id;

\echo '--- 4.4 passenger_count running-balance reconciliation (checks the generator arithmetic, not a schema rule) ---'
WITH ordered AS (
    SELECT pc.trip_id, pc.stop_id, rs.stop_sequence,
           pc.boardings, pc.alightings, pc.passenger_count,
           LAG(pc.passenger_count) OVER (
               PARTITION BY pc.trip_id ORDER BY rs.stop_sequence
           ) AS prev_passenger_count
    FROM passenger_counts pc
    JOIN trips t        ON t.trip_id = pc.trip_id
    JOIN route_stops rs ON rs.route_id = t.route_id AND rs.stop_id = pc.stop_id
)
SELECT trip_id, stop_id, stop_sequence,
       COALESCE(prev_passenger_count, 0) AS prev_passenger_count,
       boardings, alightings, passenger_count,
       COALESCE(prev_passenger_count, 0) - alightings + boardings AS expected_passenger_count
FROM ordered
WHERE passenger_count <> COALESCE(prev_passenger_count, 0) - alightings + boardings
ORDER BY trip_id, stop_sequence;

\echo '--- 4.5 Trips departing outside the documented 05:00-23:00 window, excluding Night Service ---'
SELECT tr.trip_id, r.route_id, r.route_type, tr.scheduled_departure
FROM trips tr JOIN routes r ON r.route_id = tr.route_id
WHERE r.route_type <> 'Night Service'
  AND (tr.scheduled_departure::time < TIME '05:00' OR tr.scheduled_departure::time > TIME '23:00')
ORDER BY r.route_id, tr.scheduled_departure;

\echo '--- 4.6 service_date outside the documented 30-day simulation window ---'
SELECT MIN(service_date) AS earliest, MAX(service_date) AS latest,
       COUNT(*) FILTER (WHERE service_date NOT BETWEEN DATE '2026-07-01' AND DATE '2026-07-30') AS violations
FROM trips;


-- =============================================================================
-- 5. PLAUSIBILITY — flagged for review per docs/assumptions.md ("occupancy
--    exceeding physically plausible limits is flagged, not silently
--    accepted"). These are NOT treated as hard errors.
-- =============================================================================
\echo '--- 5.1 Occupancy ratio by route_type and period (peak vs off-peak) ---'
WITH occ AS (
    SELECT r.route_type,
           CASE WHEN pc."timestamp"::time BETWEEN TIME '07:00' AND TIME '10:00'
                  OR pc."timestamp"::time BETWEEN TIME '17:00' AND TIME '20:00'
                THEN 'peak' ELSE 'off_peak' END AS period,
           pc.passenger_count::numeric / b.capacity AS occupancy_ratio
    FROM passenger_counts pc
    JOIN trips t  ON t.trip_id = pc.trip_id
    JOIN routes r ON r.route_id = t.route_id
    JOIN buses b  ON b.bus_id = t.bus_id
)
SELECT route_type, period,
       ROUND(AVG(occupancy_ratio), 2) AS mean_occupancy_ratio,
       ROUND(MAX(occupancy_ratio), 2) AS max_occupancy_ratio,
       COUNT(*) FILTER (WHERE occupancy_ratio > 1.5) AS records_over_150pct
FROM occ
GROUP BY route_type, period
ORDER BY route_type, period;

\echo '--- 5.2 Stop-level records flagged as implausible (occupancy > 200% of capacity) ---'
SELECT pc.trip_id, pc.stop_id, r.route_type, pc.passenger_count, b.capacity,
       ROUND(pc.passenger_count::numeric / b.capacity, 2) AS occupancy_ratio
FROM passenger_counts pc
JOIN trips t  ON t.trip_id = pc.trip_id
JOIN routes r ON r.route_id = t.route_id
JOIN buses b  ON b.bus_id = t.bus_id
WHERE pc.passenger_count::numeric / b.capacity > 2.0
ORDER BY occupancy_ratio DESC;


-- =============================================================================
-- 6. CALIBRATION SANITY CHECKS — confirm the generator hit documented
--    targets from docs/assumptions.md. Informational, not pass/fail.
-- =============================================================================
\echo '--- 6.1 Total fleet size (documented target: ~556 buses) ---'
SELECT COUNT(*) AS total_buses FROM buses;

\echo '--- 6.2 On-time performance overall (on-time = arrival <= scheduled + 5 min) ---'
SELECT ROUND(100.0 * COUNT(*) FILTER (
           WHERE actual_arrival <= scheduled_arrival + INTERVAL '5 minutes'
       ) / COUNT(*), 1) AS pct_on_time
FROM trips;

\echo '--- 6.3 Weekday vs weekend ridership (documented target: Sat ~0.85x, Sun ~0.65x of weekday) ---'
SELECT CASE EXTRACT(DOW FROM t.service_date)
           WHEN 0 THEN 'Sunday' WHEN 6 THEN 'Saturday' ELSE 'Weekday' END AS day_type,
       SUM(pc.boardings) AS total_boardings,
       COUNT(DISTINCT t.service_date) AS n_days,
       ROUND(SUM(pc.boardings)::numeric / COUNT(DISTINCT t.service_date), 0) AS avg_boardings_per_day
FROM passenger_counts pc
JOIN trips t ON t.trip_id = pc.trip_id
GROUP BY 1
ORDER BY 1;
