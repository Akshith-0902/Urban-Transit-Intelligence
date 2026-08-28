-- =============================================================================
-- 06_advanced_analysis.sql
-- Purpose: Cross-cutting/advanced queries (route clustering inputs, supply-demand
--          mismatch ranking, etc.) — populated as needed beyond the core 4 layers
-- Phase: 3 (SQL Analytics) / optional advanced scope
-- Status: DONE
--
-- This file combines demand (02), performance (03), and capacity (04) into
-- route-level composite views for Phase 4 (Python EDA/clustering), Phase 5
-- (Power BI), and Phase 6 (recommendations). It stops short of quantified
-- what-if simulation (e.g. "move 3 buses from route X to Y, new headway is
-- Z") — that is explicitly Phase 7's scope (python/05_scenario_model.py) per
-- docs/business_requirements.md. Here we rank and flag candidates; we do not
-- simulate the outcome of reallocating them.
--
-- Run: psql -d urban_transit_intelligence -f sql/06_advanced_analysis.sql
-- =============================================================================


-- =============================================================================
-- 1. ROUTE SCORECARD — one row per route, the master feature table for
--    Phase 4 clustering / Phase 5 dashboard / Phase 6 recommendations.
-- =============================================================================
\echo '--- 1.1 Route scorecard: demand, performance, and capacity in one view ---'
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
       r.total_distance_km, r.scheduled_duration_min,
       d.total_boardings, d.avg_boardings_per_day,
       p.total_trips, p.buses_used, p.pct_on_time, p.avg_delay_minutes,
       c.avg_occupancy_ratio, c.avg_peak_occupancy, c.max_occupancy_ratio
FROM routes r
JOIN demand d      ON d.route_id = r.route_id
JOIN performance p ON p.route_id = r.route_id
JOIN capacity c    ON c.route_id = r.route_id
ORDER BY d.total_boardings DESC;


-- =============================================================================
-- 2. HEADWAY AND ESTIMATED WAITING TIME
--    Headway = gap between consecutive scheduled departures on the same
--    route/day, computed via LAG (the data doesn't store a "headway"
--    column, so this is derived directly from the trip schedule — not an
--    assumption). Estimated wait = headway / 2, per docs/assumptions.md
--    rule #3 ("approximated as headway/2 when direct passenger-arrival
--    timestamps are unavailable").
-- =============================================================================
\echo '--- 2.1 Average scheduled headway and estimated wait time by route, peak vs off-peak ---'
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
GROUP BY g.route_id, r.route_number, r.route_type, 4
ORDER BY r.route_type, g.route_id, period;


-- =============================================================================
-- 3. SUPPLY-DEMAND MISMATCH RANKING
--    Combines peak occupancy (demand pressure per seat) with fleet size
--    (buses_used) into a single ranking. Routes at the top are the clearest
--    "needs more capacity" cases; routes at the bottom are the clearest
--    "capacity could be released" cases. This is a ranking/flagging tool,
--    not a reallocation plan — geographic/depot feasibility is out of
--    scope for this project (docs/business_requirements.md > Scope).
-- =============================================================================
\echo '--- 3.1 Top 10 overcrowded routes (highest peak occupancy, ranked for capacity addition) ---'
WITH per_route AS (
    SELECT r.route_id, r.route_number, r.route_type,
           COUNT(DISTINCT t.bus_id) AS buses_used,
           ROUND(AVG(pc.passenger_count::numeric / b.capacity) FILTER (
               WHERE pc."timestamp"::time BETWEEN TIME '07:00' AND TIME '10:00'
                  OR pc."timestamp"::time BETWEEN TIME '17:00' AND TIME '20:00'
           ), 2) AS avg_peak_occupancy
    FROM passenger_counts pc
    JOIN trips t  ON t.trip_id = pc.trip_id
    JOIN routes r ON r.route_id = t.route_id
    JOIN buses b  ON b.bus_id = t.bus_id
    GROUP BY r.route_id, r.route_number, r.route_type
)
SELECT route_id, route_number, route_type, buses_used, avg_peak_occupancy
FROM per_route
WHERE avg_peak_occupancy IS NOT NULL
ORDER BY avg_peak_occupancy DESC
LIMIT 10;

\echo '--- 3.2 Top 10 underutilized routes (lowest overall occupancy, ranked as release-capacity candidates) ---'
WITH per_route AS (
    SELECT r.route_id, r.route_number, r.route_type,
           COUNT(DISTINCT t.bus_id)                                  AS buses_used,
           ROUND(AVG(pc.passenger_count::numeric / b.capacity), 2)   AS avg_occupancy_ratio
    FROM passenger_counts pc
    JOIN trips t  ON t.trip_id = pc.trip_id
    JOIN routes r ON r.route_id = t.route_id
    JOIN buses b  ON b.bus_id = t.bus_id
    GROUP BY r.route_id, r.route_number, r.route_type
)
SELECT route_id, route_number, route_type, buses_used, avg_occupancy_ratio
FROM per_route
ORDER BY avg_occupancy_ratio ASC
LIMIT 10;

\echo '--- 3.3 Illustrative pairing: same-bus_type donor/receiver candidates (diagnostic only, not a simulated outcome) ---'
WITH bus_type_map AS (
    -- each route's dominant bus_type, inferred from the buses actually used on it
    SELECT DISTINCT ON (t.route_id) t.route_id, b.bus_type
    FROM trips t JOIN buses b ON b.bus_id = t.bus_id
    GROUP BY t.route_id, b.bus_type, t.route_id
    ORDER BY t.route_id, COUNT(*) DESC
),
occ AS (
    SELECT r.route_id, r.route_number,
           ROUND(AVG(pc.passenger_count::numeric / b.capacity) FILTER (
               WHERE pc."timestamp"::time BETWEEN TIME '07:00' AND TIME '10:00'
                  OR pc."timestamp"::time BETWEEN TIME '17:00' AND TIME '20:00'
           ), 2) AS avg_peak_occupancy,
           ROUND(AVG(pc.passenger_count::numeric / b.capacity), 2) AS avg_overall_occupancy
    FROM passenger_counts pc
    JOIN trips t  ON t.trip_id = pc.trip_id
    JOIN routes r ON r.route_id = t.route_id
    JOIN buses b  ON b.bus_id = t.bus_id
    GROUP BY r.route_id, r.route_number
),
receivers AS (
    SELECT bt.bus_type, o.route_id, o.route_number, o.avg_peak_occupancy,
           ROW_NUMBER() OVER (PARTITION BY bt.bus_type ORDER BY o.avg_peak_occupancy DESC) AS rk
    FROM occ o JOIN bus_type_map bt ON bt.route_id = o.route_id
    WHERE o.avg_peak_occupancy IS NOT NULL
),
donors AS (
    SELECT bt.bus_type, o.route_id, o.route_number, o.avg_overall_occupancy,
           ROW_NUMBER() OVER (PARTITION BY bt.bus_type ORDER BY o.avg_overall_occupancy ASC) AS rk
    FROM occ o JOIN bus_type_map bt ON bt.route_id = o.route_id
)
SELECT rec.bus_type,
       rec.route_id AS overcrowded_route_id, rec.route_number AS overcrowded_route,
       rec.avg_peak_occupancy,
       don.route_id AS donor_candidate_route_id, don.route_number AS donor_candidate_route,
       don.avg_overall_occupancy AS donor_avg_occupancy
FROM receivers rec
JOIN donors don ON don.bus_type = rec.bus_type AND don.rk = rec.rk
WHERE rec.rk <= 5
  AND rec.route_id <> don.route_id  -- a route can't donate buses to itself; bus_types with
                                     -- only one route (e.g. AC Electric here) simply have no
                                     -- same-type donor candidate and are correctly absent below
ORDER BY rec.bus_type, rec.rk;


-- =============================================================================
-- 4. PRIORITY STOPS FOR GEOSPATIAL FOLLOW-UP (Phase 4)
--    Stops that are BOTH high-demand AND high-estimated-delay — the
--    strongest candidates for on-the-ground investigation (e.g. inadequate
--    dwell time, junction congestion). Reuses the same interpolated
--    stop-delay logic as sql/05_delay_analysis.sql section 2.
-- =============================================================================
\echo '--- 4.1 Stops in the top quartile for BOTH demand and estimated delay ---'
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
    SELECT PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY d.total_activity)        AS q3_activity,
           PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY sd.avg_estimated_delay_min) AS q3_delay
    FROM demand d JOIN stop_delay sd ON sd.stop_id = d.stop_id
)
SELECT s.stop_id, s.stop_name, s.zone,
       d.total_activity, ROUND(sd.avg_estimated_delay_min, 1) AS avg_estimated_delay_min
FROM demand d
JOIN stop_delay sd ON sd.stop_id = d.stop_id
JOIN stops s        ON s.stop_id = d.stop_id
CROSS JOIN thresholds th
WHERE d.total_activity >= th.q3_activity
  AND sd.avg_estimated_delay_min >= th.q3_delay
ORDER BY d.total_activity DESC;
