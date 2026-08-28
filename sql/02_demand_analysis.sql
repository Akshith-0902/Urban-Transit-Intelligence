-- =============================================================================
-- 02_demand_analysis.sql
-- Purpose: Total demand by route/stop, busiest hours, weekday vs weekend,
--          peak-concentration vs consistently-low-demand routes
-- Phase: 3 (SQL Analytics)
-- Status: DONE
--
-- Business questions answered (docs/business_requirements.md > Passenger Demand):
--   - How many passengers use the network, and which routes/stops see the
--     highest volume?
--   - What are the busiest hours? How does demand differ weekday vs. weekend?
--   - Which routes have highly concentrated peak demand vs. consistently
--     low demand?
--
-- Convention: "demand" = boardings (passengers newly getting on), the
-- standard ridership-volume metric. passenger_count (onboard load) is used
-- instead wherever the question is about crowding rather than volume — that
-- lives in 04_capacity_analysis.sql. Peak windows (07:00-10:00, 17:00-20:00)
-- match docs/assumptions.md and sql/01_data_validation.sql for consistency
-- across the project.
--
-- Run: psql -d urban_transit_intelligence -f sql/02_demand_analysis.sql
-- =============================================================================


-- =============================================================================
-- 1. NETWORK-WIDE TOTALS
-- =============================================================================
\echo '--- 1.1 Total network ridership over the 30-day window ---'
SELECT COUNT(*)                    AS total_stop_events,
       SUM(boardings)              AS total_boardings,
       SUM(alightings)             AS total_alightings,
       COUNT(DISTINCT trip_id)     AS total_trips_with_ridership
FROM passenger_counts;

\echo '--- 1.2 Total ridership by route_type tier ---'
SELECT r.route_type,
       SUM(pc.boardings)                                              AS total_boardings,
       ROUND(100.0 * SUM(pc.boardings) / SUM(SUM(pc.boardings)) OVER (), 1) AS pct_of_network
FROM passenger_counts pc
JOIN trips t  ON t.trip_id = pc.trip_id
JOIN routes r ON r.route_id = t.route_id
GROUP BY r.route_type
ORDER BY total_boardings DESC;


-- =============================================================================
-- 2. DEMAND BY ROUTE
-- =============================================================================
\echo '--- 2.1 Top 15 routes by total boardings ---'
SELECT r.route_id, r.route_number, r.route_name, r.route_type,
       SUM(pc.boardings)                          AS total_boardings,
       ROUND(SUM(pc.boardings)::numeric / 30, 0)  AS avg_boardings_per_day,
       COUNT(DISTINCT t.trip_id)                  AS total_trips
FROM passenger_counts pc
JOIN trips t  ON t.trip_id = pc.trip_id
JOIN routes r ON r.route_id = t.route_id
GROUP BY r.route_id, r.route_number, r.route_name, r.route_type
ORDER BY total_boardings DESC
LIMIT 15;

\echo '--- 2.2 Bottom 15 routes by total boardings (lowest-demand routes) ---'
SELECT r.route_id, r.route_number, r.route_name, r.route_type,
       SUM(pc.boardings)                          AS total_boardings,
       ROUND(SUM(pc.boardings)::numeric / 30, 0)  AS avg_boardings_per_day
FROM passenger_counts pc
JOIN trips t  ON t.trip_id = pc.trip_id
JOIN routes r ON r.route_id = t.route_id
GROUP BY r.route_id, r.route_number, r.route_name, r.route_type
ORDER BY total_boardings ASC
LIMIT 15;


-- =============================================================================
-- 3. DEMAND BY STOP
-- =============================================================================
\echo '--- 3.1 Top 15 busiest stops by total activity (boardings + alightings) ---'
SELECT s.stop_id, s.stop_name, s.zone,
       SUM(pc.boardings)                    AS total_boardings,
       SUM(pc.alightings)                   AS total_alightings,
       SUM(pc.boardings + pc.alightings)    AS total_activity,
       COUNT(DISTINCT t.route_id)           AS routes_served
FROM passenger_counts pc
JOIN stops s ON s.stop_id = pc.stop_id
JOIN trips t ON t.trip_id = pc.trip_id
GROUP BY s.stop_id, s.stop_name, s.zone
ORDER BY total_activity DESC
LIMIT 15;

\echo '--- 3.2 Stops ranked by net boardings minus alightings (origin-heavy vs destination-heavy) ---'
SELECT s.stop_id, s.stop_name,
       SUM(pc.boardings)  AS total_boardings,
       SUM(pc.alightings) AS total_alightings,
       SUM(pc.boardings) - SUM(pc.alightings) AS net_boardings_minus_alightings
FROM passenger_counts pc
JOIN stops s ON s.stop_id = pc.stop_id
GROUP BY s.stop_id, s.stop_name
HAVING SUM(pc.boardings) + SUM(pc.alightings) > 0
ORDER BY net_boardings_minus_alightings DESC
LIMIT 10;


-- =============================================================================
-- 4. BUSIEST HOURS (network-wide time-of-day demand profile)
-- =============================================================================
\echo '--- 4.1 Total boardings by hour of day (network-wide) ---'
SELECT EXTRACT(HOUR FROM "timestamp")::int AS hour_of_day,
       SUM(boardings)                       AS total_boardings,
       ROUND(100.0 * SUM(boardings) / SUM(SUM(boardings)) OVER (), 1) AS pct_of_daily_boardings
FROM passenger_counts
GROUP BY 1
ORDER BY 1;

\echo '--- 4.2 Busiest single hour per route_type tier ---'
WITH hourly AS (
    SELECT r.route_type,
           EXTRACT(HOUR FROM pc."timestamp")::int AS hour_of_day,
           SUM(pc.boardings)                       AS total_boardings
    FROM passenger_counts pc
    JOIN trips t  ON t.trip_id = pc.trip_id
    JOIN routes r ON r.route_id = t.route_id
    GROUP BY r.route_type, EXTRACT(HOUR FROM pc."timestamp")
)
SELECT DISTINCT ON (route_type)
       route_type, hour_of_day AS busiest_hour, total_boardings
FROM hourly
ORDER BY route_type, total_boardings DESC;


-- =============================================================================
-- 5. WEEKDAY VS WEEKEND DEMAND
-- =============================================================================
\echo '--- 5.1 Weekday vs Saturday vs Sunday, network-wide (sanity-checks calibration targets: Sat ~0.85x, Sun ~0.65x) ---'
SELECT CASE EXTRACT(DOW FROM t.service_date)
           WHEN 0 THEN 'Sunday' WHEN 6 THEN 'Saturday' ELSE 'Weekday' END AS day_type,
       COUNT(DISTINCT t.service_date)                          AS n_days,
       SUM(pc.boardings)                                       AS total_boardings,
       ROUND(SUM(pc.boardings)::numeric / COUNT(DISTINCT t.service_date), 0) AS avg_boardings_per_day
FROM passenger_counts pc
JOIN trips t ON t.trip_id = pc.trip_id
GROUP BY 1
ORDER BY 1;

\echo '--- 5.2 Weekday vs weekend demand by route_type ---'
SELECT r.route_type,
       CASE WHEN EXTRACT(DOW FROM t.service_date) IN (0,6) THEN 'Weekend' ELSE 'Weekday' END AS day_type,
       ROUND(SUM(pc.boardings)::numeric / COUNT(DISTINCT t.service_date), 0) AS avg_boardings_per_day
FROM passenger_counts pc
JOIN trips t  ON t.trip_id = pc.trip_id
JOIN routes r ON r.route_id = t.route_id
GROUP BY r.route_type, 2
ORDER BY r.route_type, day_type;


-- =============================================================================
-- 6. PEAK-CONCENTRATED VS CONSISTENTLY-LOW-DEMAND ROUTES
--    "Peak concentration" = share of a route's total boardings that occur in
--    the two documented peak windows (07:00-10:00, 17:00-20:00). High share
--    = spiky commuter route; low share + low absolute volume = consistently
--    low-demand candidate for the resource-allocation phase (Phase 6).
-- =============================================================================
\echo '--- 6.1 Peak-concentration ratio per route (top 10 most peak-concentrated) ---'
WITH per_route AS (
    SELECT r.route_id, r.route_number, r.route_type,
           SUM(pc.boardings) AS total_boardings,
           SUM(pc.boardings) FILTER (
               WHERE pc."timestamp"::time BETWEEN TIME '07:00' AND TIME '10:00'
                  OR pc."timestamp"::time BETWEEN TIME '17:00' AND TIME '20:00'
           ) AS peak_boardings
    FROM passenger_counts pc
    JOIN trips t  ON t.trip_id = pc.trip_id
    JOIN routes r ON r.route_id = t.route_id
    GROUP BY r.route_id, r.route_number, r.route_type
)
SELECT route_id, route_number, route_type, total_boardings,
       ROUND(100.0 * peak_boardings / NULLIF(total_boardings, 0), 1) AS pct_boardings_in_peak
FROM per_route
ORDER BY pct_boardings_in_peak DESC
LIMIT 10;

\echo '--- 6.2 Consistently low-demand routes: bottom-quartile total volume AND below-median peak concentration ---'
WITH per_route AS (
    SELECT r.route_id, r.route_number, r.route_type,
           SUM(pc.boardings) AS total_boardings,
           SUM(pc.boardings) FILTER (
               WHERE pc."timestamp"::time BETWEEN TIME '07:00' AND TIME '10:00'
                  OR pc."timestamp"::time BETWEEN TIME '17:00' AND TIME '20:00'
           )::numeric / NULLIF(SUM(pc.boardings), 0) AS peak_share
    FROM passenger_counts pc
    JOIN trips t  ON t.trip_id = pc.trip_id
    JOIN routes r ON r.route_id = t.route_id
    GROUP BY r.route_id, r.route_number, r.route_type
),
thresholds AS (
    SELECT PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY total_boardings) AS q1_volume,
           PERCENTILE_CONT(0.5)  WITHIN GROUP (ORDER BY peak_share)      AS median_peak_share
    FROM per_route
)
SELECT pr.route_id, pr.route_number, pr.route_type,
       pr.total_boardings, ROUND(pr.peak_share * 100, 1) AS pct_boardings_in_peak
FROM per_route pr, thresholds th
WHERE pr.total_boardings <= th.q1_volume
  AND pr.peak_share <= th.median_peak_share
ORDER BY pr.total_boardings ASC;


-- =============================================================================
-- 7. DAILY DEMAND TREND (network-wide, all 30 days — feeds Phase 4 EDA charting)
-- =============================================================================
\echo '--- 7.1 Total boardings per service_date ---'
SELECT t.service_date,
       TO_CHAR(t.service_date, 'Dy') AS weekday,
       SUM(pc.boardings)              AS total_boardings
FROM passenger_counts pc
JOIN trips t ON t.trip_id = pc.trip_id
GROUP BY t.service_date
ORDER BY t.service_date;
