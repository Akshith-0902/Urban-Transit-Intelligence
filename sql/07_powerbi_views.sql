-- =============================================================================
-- 07_powerbi_views.sql
-- Purpose: Single source-of-truth views for the Phase 5 Power BI dashboard.
--          No new business logic is introduced here — every definition
--          (on-time = arrival within 5 min of schedule; peak = 07:00-10:00
--          / 17:00-20:00; occupancy ratio = passengers/capacity; priority
--          stop = top quartile on both demand and estimated delay) is
--          copied from the already-audited sql/03, sql/04, sql/05,
--          sql/06 files. Power BI imports these views instead of
--          re-deriving the logic in DAX.
-- Phase: 5 (Power BI Dashboard)
--
-- Run: psql -d urban_transit_intelligence -f sql/07_powerbi_views.sql
-- =============================================================================

DROP VIEW IF EXISTS vw_priority_stops CASCADE;
DROP VIEW IF EXISTS vw_stop_geo_summary CASCADE;
DROP VIEW IF EXISTS vw_route_headway CASCADE;
DROP VIEW IF EXISTS vw_route_scorecard CASCADE;
DROP VIEW IF EXISTS vw_passenger_activity CASCADE;
DROP VIEW IF EXISTS vw_trip_performance CASCADE;

-- -----------------------------------------------------------------------------
-- 1. TRIP PERFORMANCE — one row per trip, the fact table behind the
--    Route Performance & Reliability page. Same on-time/delay definitions
--    as sql/03_route_performance.sql.
-- -----------------------------------------------------------------------------
CREATE VIEW vw_trip_performance AS
SELECT
    t.trip_id,
    t.route_id,
    r.route_number,
    r.route_name,
    r.route_type,
    t.bus_id,
    b.bus_type,
    t.service_date,
    TRIM(TO_CHAR(t.service_date, 'Day'))                              AS day_of_week,
    EXTRACT(ISODOW FROM t.service_date) IN (6, 7)                      AS is_weekend,
    t.scheduled_departure,
    t.actual_departure,
    t.scheduled_arrival,
    t.actual_arrival,
    EXTRACT(HOUR FROM t.scheduled_departure)::int                      AS hour_of_day,
    (t.scheduled_departure::time BETWEEN TIME '07:00' AND TIME '10:00'
        OR t.scheduled_departure::time BETWEEN TIME '17:00' AND TIME '20:00') AS is_peak,
    ROUND(EXTRACT(EPOCH FROM (t.actual_arrival - t.scheduled_arrival)) / 60, 1) AS delay_minutes,
    (t.actual_arrival <= t.scheduled_arrival + INTERVAL '5 minutes')    AS is_on_time,
    r.scheduled_duration_min,
    ROUND(EXTRACT(EPOCH FROM (t.actual_arrival - t.actual_departure)) / 60, 1) AS actual_duration_min
FROM trips t
JOIN routes r ON r.route_id = t.route_id
JOIN buses  b ON b.bus_id   = t.bus_id;

-- -----------------------------------------------------------------------------
-- 2. PASSENGER ACTIVITY — one row per stop-visit, the fact table behind
--    the Demand and Capacity/Utilization pages. Occupancy ratio matches
--    sql/04_capacity_analysis.sql.
-- -----------------------------------------------------------------------------
CREATE VIEW vw_passenger_activity AS
SELECT
    pc.trip_id,
    t.route_id,
    r.route_number,
    r.route_type,
    pc.stop_id,
    s.stop_name,
    s.zone,
    s.latitude,
    s.longitude,
    pc."timestamp",
    EXTRACT(HOUR FROM pc."timestamp")::int                             AS hour_of_day,
    EXTRACT(ISODOW FROM pc."timestamp") IN (6, 7)                       AS is_weekend,
    (pc."timestamp"::time BETWEEN TIME '07:00' AND TIME '10:00'
        OR pc."timestamp"::time BETWEEN TIME '17:00' AND TIME '20:00') AS is_peak,
    pc.boardings,
    pc.alightings,
    pc.passenger_count,
    b.capacity                                                        AS bus_capacity,
    ROUND(pc.passenger_count::numeric / b.capacity, 2)                 AS occupancy_ratio
FROM passenger_counts pc
JOIN trips t  ON t.trip_id  = pc.trip_id
JOIN routes r ON r.route_id = t.route_id
JOIN buses  b ON b.bus_id   = t.bus_id
JOIN stops  s ON s.stop_id  = pc.stop_id;

-- -----------------------------------------------------------------------------
-- 3. ROUTE SCORECARD — one row per route; identical to
--    sql/06_advanced_analysis.sql §1.1, materialized as a view for the
--    Route Scorecard page (scatter: delay vs. occupancy, bubble = demand).
-- -----------------------------------------------------------------------------
CREATE VIEW vw_route_scorecard AS
WITH demand AS (
    SELECT t.route_id,
           SUM(pc.boardings)                          AS total_boardings,
           ROUND(SUM(pc.boardings)::numeric / 30, 0)  AS avg_boardings_per_day
    FROM passenger_counts pc JOIN trips t ON t.trip_id = pc.trip_id
    GROUP BY t.route_id
),
performance AS (
    SELECT route_id,
           COUNT(*)                                                                     AS total_trips,
           ROUND(100.0 * COUNT(*) FILTER (WHERE actual_arrival <= scheduled_arrival + INTERVAL '5 minutes')
                 / COUNT(*), 1)                                                          AS pct_on_time,
           ROUND(AVG(EXTRACT(EPOCH FROM (actual_arrival - scheduled_arrival)) / 60), 1)  AS avg_delay_minutes,
           COUNT(DISTINCT bus_id)                                                        AS buses_used
    FROM trips
    GROUP BY route_id
),
capacity AS (
    SELECT t.route_id,
           ROUND(AVG(pc.passenger_count::numeric / b.capacity), 2) AS avg_occupancy_ratio,
           ROUND(AVG(pc.passenger_count::numeric / b.capacity) FILTER (
               WHERE pc."timestamp"::time BETWEEN TIME '07:00' AND TIME '10:00'
                  OR pc."timestamp"::time BETWEEN TIME '17:00' AND TIME '20:00'
           ), 2)                                                    AS avg_peak_occupancy,
           ROUND(MAX(pc.passenger_count::numeric / b.capacity), 2)  AS max_occupancy_ratio
    FROM passenger_counts pc
    JOIN trips t ON t.trip_id = pc.trip_id
    JOIN buses b ON b.bus_id = t.bus_id
    GROUP BY t.route_id
)
SELECT r.route_id, r.route_number, r.route_name, r.route_type,
       r.origin, r.destination,
       r.total_distance_km, r.scheduled_duration_min,
       d.total_boardings, d.avg_boardings_per_day,
       p.total_trips, p.buses_used, p.pct_on_time, p.avg_delay_minutes,
       c.avg_occupancy_ratio, c.avg_peak_occupancy, c.max_occupancy_ratio
FROM routes r
JOIN demand d      ON d.route_id = r.route_id
JOIN performance p ON p.route_id = r.route_id
JOIN capacity c    ON c.route_id = r.route_id;

-- -----------------------------------------------------------------------------
-- 4. ROUTE HEADWAY / ESTIMATED WAIT — identical to
--    sql/06_advanced_analysis.sql §2.1, for the Capacity/Utilization page.
-- -----------------------------------------------------------------------------
CREATE VIEW vw_route_headway AS
WITH gaps AS (
    SELECT route_id, service_date, scheduled_departure,
           EXTRACT(EPOCH FROM (
               scheduled_departure - LAG(scheduled_departure) OVER (
                   PARTITION BY route_id, service_date ORDER BY scheduled_departure
               )
           )) / 60 AS headway_minutes
    FROM trips
)
SELECT g.route_id, r.route_number, r.route_type,
       CASE WHEN g.scheduled_departure::time BETWEEN TIME '07:00' AND TIME '10:00'
             OR g.scheduled_departure::time BETWEEN TIME '17:00' AND TIME '20:00'
            THEN 'Peak' ELSE 'Off-peak' END AS period,
       ROUND(AVG(g.headway_minutes), 1)       AS avg_headway_minutes,
       ROUND(AVG(g.headway_minutes) / 2, 1)   AS estimated_avg_wait_minutes
FROM gaps g
JOIN routes r ON r.route_id = g.route_id
WHERE g.headway_minutes IS NOT NULL
GROUP BY g.route_id, r.route_number, r.route_type, 4;

-- -----------------------------------------------------------------------------
-- 5. STOP GEO SUMMARY — one row per stop, for the Geospatial page.
--    Same interpolated stop-delay logic as sql/05_delay_analysis.sql §2 /
--    sql/06_advanced_analysis.sql §4.1, but returns ALL stops (not just
--    the top-quartile ones) with an is_priority_stop flag so the Power BI
--    map can render every stop and highlight priority ones, matching
--    reports/geospatial_summary.md.
-- -----------------------------------------------------------------------------
CREATE VIEW vw_stop_geo_summary AS
WITH demand AS (
    SELECT stop_id, SUM(boardings + alightings) AS total_activity
    FROM passenger_counts
    GROUP BY stop_id
),
stop_delay AS (
    SELECT pc.stop_id,
           AVG(EXTRACT(EPOCH FROM (
               pc."timestamp" -
               (t.scheduled_departure +
                ((rs.distance_from_origin_km / r.total_distance_km) * r.scheduled_duration_min)
                    * INTERVAL '1 minute')
           )) / 60) AS avg_estimated_delay_min
    FROM passenger_counts pc
    JOIN trips t        ON t.trip_id = pc.trip_id
    JOIN routes r       ON r.route_id = t.route_id
    JOIN route_stops rs ON rs.route_id = t.route_id AND rs.stop_id = pc.stop_id
    GROUP BY pc.stop_id
),
thresholds AS (
    SELECT PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY d.total_activity)           AS q3_activity,
           PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY sd.avg_estimated_delay_min) AS q3_delay
    FROM demand d JOIN stop_delay sd ON sd.stop_id = d.stop_id
)
SELECT s.stop_id, s.stop_name, s.zone, s.latitude, s.longitude,
       d.total_activity,
       ROUND(sd.avg_estimated_delay_min, 1) AS avg_estimated_delay_min,
       (d.total_activity >= th.q3_activity AND sd.avg_estimated_delay_min >= th.q3_delay) AS is_priority_stop
FROM demand d
JOIN stop_delay sd ON sd.stop_id = d.stop_id
JOIN stops s        ON s.stop_id = d.stop_id
CROSS JOIN thresholds th;

-- Convenience view: priority stops only (mirrors reports/geospatial_summary.md table)
CREATE VIEW vw_priority_stops AS
SELECT * FROM vw_stop_geo_summary WHERE is_priority_stop ORDER BY total_activity DESC;
