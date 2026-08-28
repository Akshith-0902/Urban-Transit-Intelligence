-- =============================================================================
-- 03_route_performance.sql
-- Purpose: On-time rate, average delay, scheduled vs actual journey time by route
-- Phase: 3 (SQL Analytics)
-- Status: DONE
--
-- Business questions answered (docs/business_requirements.md > Operational Performance):
--   - Which routes experience the most delay? What % of trips are on time?
--   - How does actual journey time differ from scheduled?
--
-- Convention: "on time" = actual_arrival <= scheduled_arrival + 5 minutes,
-- per docs/assumptions.md rule #1. Delay is measured in minutes as
-- EXTRACT(EPOCH FROM (actual_arrival - scheduled_arrival)) / 60, so a
-- negative value means the trip arrived early. Stop-level delay hotspots
-- (finer than per-trip) live in 05_delay_analysis.sql.
--
-- Run: psql -d urban_transit_intelligence -f sql/03_route_performance.sql
-- =============================================================================


-- =============================================================================
-- 1. NETWORK-WIDE ON-TIME PERFORMANCE
-- =============================================================================
\echo '--- 1.1 Overall on-time performance (sanity-checks Phase 2 finding: ~55.6%) ---'
SELECT COUNT(*)                                                          AS total_trips,
       COUNT(*) FILTER (WHERE actual_arrival <= scheduled_arrival + INTERVAL '5 minutes') AS on_time_trips,
       ROUND(100.0 * COUNT(*) FILTER (WHERE actual_arrival <= scheduled_arrival + INTERVAL '5 minutes')
             / COUNT(*), 1)                                              AS pct_on_time
FROM trips;

\echo '--- 1.2 On-time performance by route_type tier ---'
SELECT r.route_type,
       COUNT(*)                                                                 AS total_trips,
       ROUND(100.0 * COUNT(*) FILTER (WHERE t.actual_arrival <= t.scheduled_arrival + INTERVAL '5 minutes')
             / COUNT(*), 1)                                                     AS pct_on_time,
       ROUND(AVG(EXTRACT(EPOCH FROM (t.actual_arrival - t.scheduled_arrival)) / 60), 1) AS avg_delay_minutes
FROM trips t
JOIN routes r ON r.route_id = t.route_id
GROUP BY r.route_type
ORDER BY pct_on_time ASC;


-- =============================================================================
-- 2. ON-TIME RATE AND AVERAGE DELAY BY ROUTE
-- =============================================================================
\echo '--- 2.1 Worst 15 routes by average arrival delay ---'
SELECT r.route_id, r.route_number, r.route_name, r.route_type,
       COUNT(*)                                                            AS total_trips,
       ROUND(AVG(EXTRACT(EPOCH FROM (t.actual_arrival - t.scheduled_arrival)) / 60), 1) AS avg_delay_minutes,
       ROUND(100.0 * COUNT(*) FILTER (WHERE t.actual_arrival <= t.scheduled_arrival + INTERVAL '5 minutes')
             / COUNT(*), 1)                                                AS pct_on_time
FROM trips t
JOIN routes r ON r.route_id = t.route_id
GROUP BY r.route_id, r.route_number, r.route_name, r.route_type
ORDER BY avg_delay_minutes DESC
LIMIT 15;

\echo '--- 2.2 Best 15 routes by average arrival delay (most reliable) ---'
SELECT r.route_id, r.route_number, r.route_name, r.route_type,
       COUNT(*)                                                            AS total_trips,
       ROUND(AVG(EXTRACT(EPOCH FROM (t.actual_arrival - t.scheduled_arrival)) / 60), 1) AS avg_delay_minutes,
       ROUND(100.0 * COUNT(*) FILTER (WHERE t.actual_arrival <= t.scheduled_arrival + INTERVAL '5 minutes')
             / COUNT(*), 1)                                                AS pct_on_time
FROM trips t
JOIN routes r ON r.route_id = t.route_id
GROUP BY r.route_id, r.route_number, r.route_name, r.route_type
ORDER BY avg_delay_minutes ASC
LIMIT 15;


-- =============================================================================
-- 3. SCHEDULED VS ACTUAL JOURNEY TIME
-- =============================================================================
\echo '--- 3.1 Scheduled vs actual average journey time by route (top 15 by absolute time overrun) ---'
SELECT r.route_id, r.route_number, r.route_name, r.route_type,
       r.scheduled_duration_min,
       ROUND(AVG(EXTRACT(EPOCH FROM (t.actual_arrival - t.actual_departure)) / 60), 1) AS avg_actual_duration_min,
       ROUND(AVG(EXTRACT(EPOCH FROM (t.actual_arrival - t.actual_departure)) / 60)
             - r.scheduled_duration_min, 1)                                            AS avg_overrun_min,
       ROUND(100.0 * (AVG(EXTRACT(EPOCH FROM (t.actual_arrival - t.actual_departure)) / 60)
             - r.scheduled_duration_min) / r.scheduled_duration_min, 1)                AS pct_overrun
FROM trips t
JOIN routes r ON r.route_id = t.route_id
GROUP BY r.route_id, r.route_number, r.route_name, r.route_type, r.scheduled_duration_min
ORDER BY avg_overrun_min DESC
LIMIT 15;

\echo '--- 3.2 Journey-time overrun by route_type tier (network view) ---'
SELECT r.route_type,
       ROUND(AVG(r.scheduled_duration_min), 1)                                          AS avg_scheduled_duration_min,
       ROUND(AVG(EXTRACT(EPOCH FROM (t.actual_arrival - t.actual_departure)) / 60), 1)   AS avg_actual_duration_min,
       ROUND(AVG(EXTRACT(EPOCH FROM (t.actual_arrival - t.actual_departure)) / 60)
             - AVG(r.scheduled_duration_min), 1)                                        AS avg_overrun_min
FROM trips t
JOIN routes r ON r.route_id = t.route_id
GROUP BY r.route_type
ORDER BY avg_overrun_min DESC;


-- =============================================================================
-- 4. WHEN DELAYS HAPPEN (time-of-day and calendar patterns)
-- =============================================================================
\echo '--- 4.1 On-time performance by scheduled departure hour ---'
SELECT EXTRACT(HOUR FROM t.scheduled_departure)::int AS departure_hour,
       COUNT(*)                                                                 AS total_trips,
       ROUND(100.0 * COUNT(*) FILTER (WHERE t.actual_arrival <= t.scheduled_arrival + INTERVAL '5 minutes')
             / COUNT(*), 1)                                                     AS pct_on_time,
       ROUND(AVG(EXTRACT(EPOCH FROM (t.actual_arrival - t.scheduled_arrival)) / 60), 1) AS avg_delay_minutes
FROM trips t
GROUP BY 1
ORDER BY 1;

\echo '--- 4.2 On-time performance: weekday vs weekend ---'
SELECT CASE WHEN EXTRACT(DOW FROM t.service_date) IN (0,6) THEN 'Weekend' ELSE 'Weekday' END AS day_type,
       COUNT(*)                                                                 AS total_trips,
       ROUND(100.0 * COUNT(*) FILTER (WHERE t.actual_arrival <= t.scheduled_arrival + INTERVAL '5 minutes')
             / COUNT(*), 1)                                                     AS pct_on_time,
       ROUND(AVG(EXTRACT(EPOCH FROM (t.actual_arrival - t.scheduled_arrival)) / 60), 1) AS avg_delay_minutes
FROM trips t
GROUP BY 1
ORDER BY 1;

\echo '--- 4.3 On-time performance trend by service_date (network-wide) ---'
SELECT t.service_date,
       ROUND(100.0 * COUNT(*) FILTER (WHERE t.actual_arrival <= t.scheduled_arrival + INTERVAL '5 minutes')
             / COUNT(*), 1) AS pct_on_time
FROM trips t
GROUP BY t.service_date
ORDER BY t.service_date;


-- =============================================================================
-- 5. FLEET-SIDE VIEW: does bus_type correlate with reliability?
--    (buses aren't FK'd to a single route in the schema, but each bus is
--    drawn from a route-dedicated pool by construction — see
--    python/01_generate_synthetic_operations.py — so this is a legitimate,
--    schema-safe way to look at reliability by bus_type without assuming
--    an explicit bus->route relationship.)
-- =============================================================================
\echo '--- 5.1 On-time performance and average delay by bus_type ---'
SELECT b.bus_type,
       COUNT(*)                                                                 AS total_trips,
       COUNT(DISTINCT t.bus_id)                                                 AS distinct_buses,
       ROUND(100.0 * COUNT(*) FILTER (WHERE t.actual_arrival <= t.scheduled_arrival + INTERVAL '5 minutes')
             / COUNT(*), 1)                                                     AS pct_on_time,
       ROUND(AVG(EXTRACT(EPOCH FROM (t.actual_arrival - t.scheduled_arrival)) / 60), 1) AS avg_delay_minutes
FROM trips t
JOIN buses b ON b.bus_id = t.bus_id
GROUP BY b.bus_type
ORDER BY pct_on_time ASC;
