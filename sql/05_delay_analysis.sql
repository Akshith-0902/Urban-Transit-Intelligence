-- =============================================================================
-- 05_delay_analysis.sql
-- Purpose: Delay hotspots by route/stop/hour; delay distribution
-- Phase: 3 (SQL Analytics)
-- Status: DONE
--
-- Business questions answered (docs/business_requirements.md > Operational
-- Performance / Geographic Analysis):
--   - Which stops contribute to excessive journey times?
--   - Where are delays geographically/temporally concentrated?
--
-- IMPORTANT — stop-level delay is a DERIVED/ESTIMATED metric, not a stored
-- one. The schema only stores scheduled_departure/scheduled_arrival at the
-- TRIP level (see sql/00_schema.sql) — there is no scheduled time per stop.
-- Section 2 below interpolates an expected arrival time at each stop by
-- distributing the trip's scheduled duration proportionally along
-- route_stops.distance_from_origin_km (a standard schedule-interpolation
-- technique, and consistent with this project's stated practice in
-- docs/assumptions.md of clearly flagging every derived value). Treat
-- stop-level delay as an approximation for spotting hotspots, not a
-- precise measurement — trip-level delay (sql/03_route_performance.sql) is
-- the reliable figure.
--
-- Run: psql -d urban_transit_intelligence -f sql/05_delay_analysis.sql
-- =============================================================================


-- =============================================================================
-- 1. NETWORK-WIDE DELAY DISTRIBUTION (trip-level, reliable — not interpolated)
-- =============================================================================
\echo '--- 1.1 Delay distribution buckets (trip-level arrival delay) ---'
WITH d AS (
    SELECT EXTRACT(EPOCH FROM (actual_arrival - scheduled_arrival)) / 60 AS delay_minutes
    FROM trips
)
SELECT CASE
           WHEN delay_minutes <= 5  THEN '1. On time (<=5 min)'
           WHEN delay_minutes <= 15 THEN '2. Minor (5-15 min)'
           WHEN delay_minutes <= 30 THEN '3. Moderate (15-30 min)'
           ELSE '4. Severe (>30 min)'
       END AS delay_bucket,
       COUNT(*)                                            AS trip_count,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1)  AS pct_of_trips
FROM d
GROUP BY 1
ORDER BY 1;

\echo '--- 1.2 Delay distribution by route_type ---'
WITH d AS (
    SELECT r.route_type,
           EXTRACT(EPOCH FROM (t.actual_arrival - t.scheduled_arrival)) / 60 AS delay_minutes
    FROM trips t JOIN routes r ON r.route_id = t.route_id
)
SELECT route_type,
       CASE
           WHEN delay_minutes <= 5  THEN '1. On time (<=5 min)'
           WHEN delay_minutes <= 15 THEN '2. Minor (5-15 min)'
           WHEN delay_minutes <= 30 THEN '3. Moderate (15-30 min)'
           ELSE '4. Severe (>30 min)'
       END AS delay_bucket,
       COUNT(*) AS trip_count
FROM d
GROUP BY route_type, 2
ORDER BY route_type, delay_bucket;


-- =============================================================================
-- 2. STOP-LEVEL DELAY HOTSPOTS (interpolated — see header note above)
-- =============================================================================
\echo '--- 2.1 Top 20 stops by average estimated arrival delay ---'
WITH stop_delay AS (
    SELECT pc.stop_id,
           EXTRACT(EPOCH FROM (
               pc."timestamp" -
               (t.scheduled_departure +
                ((rs.distance_from_origin_km / r.total_distance_km) * r.scheduled_duration_min)
                    * INTERVAL '1 minute')
           )) / 60 AS estimated_stop_delay_minutes
    FROM passenger_counts pc
    JOIN trips t        ON t.trip_id = pc.trip_id
    JOIN routes r       ON r.route_id = t.route_id
    JOIN route_stops rs ON rs.route_id = t.route_id AND rs.stop_id = pc.stop_id
)
SELECT s.stop_id, s.stop_name,
       COUNT(*)                                              AS stop_events,
       ROUND(AVG(sd.estimated_stop_delay_minutes), 1)        AS avg_estimated_delay_min,
       COUNT(*) FILTER (WHERE sd.estimated_stop_delay_minutes > 15) AS events_over_15min_delay
FROM stop_delay sd
JOIN stops s ON s.stop_id = sd.stop_id
GROUP BY s.stop_id, s.stop_name
ORDER BY avg_estimated_delay_min DESC
LIMIT 20;

\echo '--- 2.2 Worst 15 route x stop combinations by average estimated delay ---'
WITH stop_delay AS (
    SELECT t.route_id, pc.stop_id,
           EXTRACT(EPOCH FROM (
               pc."timestamp" -
               (t.scheduled_departure +
                ((rs.distance_from_origin_km / r.total_distance_km) * r.scheduled_duration_min)
                    * INTERVAL '1 minute')
           )) / 60 AS estimated_stop_delay_minutes
    FROM passenger_counts pc
    JOIN trips t        ON t.trip_id = pc.trip_id
    JOIN routes r       ON r.route_id = t.route_id
    JOIN route_stops rs ON rs.route_id = t.route_id AND rs.stop_id = pc.stop_id
)
SELECT r.route_id, r.route_number, s.stop_id, s.stop_name,
       COUNT(*)                                       AS stop_events,
       ROUND(AVG(sd.estimated_stop_delay_minutes), 1) AS avg_estimated_delay_min
FROM stop_delay sd
JOIN routes r ON r.route_id = sd.route_id
JOIN stops s  ON s.stop_id = sd.stop_id
GROUP BY r.route_id, r.route_number, s.stop_id, s.stop_name
HAVING COUNT(*) >= 30   -- drop thin combinations (e.g. rare stop-route pairs) to avoid noisy outliers
ORDER BY avg_estimated_delay_min DESC
LIMIT 15;


-- =============================================================================
-- 3. WHEN DELAYS ARE WORST (hour of day, day of week)
-- =============================================================================
\echo '--- 3.1 Average trip-level delay and severe-delay count by scheduled departure hour ---'
SELECT EXTRACT(HOUR FROM t.scheduled_departure)::int AS departure_hour,
       COUNT(*)                                                                    AS total_trips,
       ROUND(AVG(EXTRACT(EPOCH FROM (t.actual_arrival - t.scheduled_arrival)) / 60), 1) AS avg_delay_minutes,
       COUNT(*) FILTER (WHERE t.actual_arrival > t.scheduled_arrival + INTERVAL '30 minutes') AS severe_delay_trips
FROM trips t
GROUP BY 1
ORDER BY 1;

\echo '--- 3.2 Average trip-level delay by day of week ---'
SELECT TO_CHAR(t.service_date, 'Dy')                                                AS weekday,
       EXTRACT(DOW FROM t.service_date)::int                                        AS dow,
       ROUND(AVG(EXTRACT(EPOCH FROM (t.actual_arrival - t.scheduled_arrival)) / 60), 1) AS avg_delay_minutes
FROM trips t
GROUP BY 1, 2
ORDER BY 2;


-- =============================================================================
-- 4. DELAY VS CROWDING — hand-off table for Phase 4 (does congestion track
--    with overcrowding, route by route? Correlation, not causation, per
--    docs/assumptions.md rule #5.)
-- =============================================================================
\echo '--- 4.1 Per-route avg delay alongside avg occupancy ratio (for Phase 4 correlation) ---'
SELECT r.route_id, r.route_number, r.route_type,
       ROUND(AVG(EXTRACT(EPOCH FROM (t.actual_arrival - t.scheduled_arrival)) / 60), 1) AS avg_delay_minutes,
       ROUND(AVG(pc.passenger_count::numeric / b.capacity), 2)                          AS avg_occupancy_ratio
FROM trips t
JOIN routes r ON r.route_id = t.route_id
JOIN buses b  ON b.bus_id = t.bus_id
JOIN passenger_counts pc ON pc.trip_id = t.trip_id
GROUP BY r.route_id, r.route_number, r.route_type
ORDER BY avg_delay_minutes DESC;
