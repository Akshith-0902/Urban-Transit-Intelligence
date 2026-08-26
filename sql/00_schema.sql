-- =============================================================================
-- 00_schema.sql
-- Purpose: Full database schema for Urban Transit Intelligence
-- Phase: 1 (Data Acquisition & Database Design)
--
-- Tables routes / stops / route_stops are populated from real data
-- (see data/raw/, data/data_dictionary.md, data/raw/SOURCES.md).
-- Tables buses / trips / passenger_counts are populated from the calibrated
-- synthetic generator (python/01_generate_synthetic_operations.py, next phase).
-- =============================================================================

DROP TABLE IF EXISTS passenger_counts CASCADE;
DROP TABLE IF EXISTS trips CASCADE;
DROP TABLE IF EXISTS buses CASCADE;
DROP TABLE IF EXISTS route_stops CASCADE;
DROP TABLE IF EXISTS stops CASCADE;
DROP TABLE IF EXISTS routes CASCADE;

-- -----------------------------------------------------------------------------
-- routes — real MTC route numbers/corridors (see data/raw/SOURCES.md)
-- -----------------------------------------------------------------------------
CREATE TABLE routes (
    route_id                VARCHAR(10)   PRIMARY KEY,
    route_number            VARCHAR(20)   NOT NULL,
    route_name              VARCHAR(150)  NOT NULL,
    route_type              VARCHAR(30)   NOT NULL
        CHECK (route_type IN ('Ordinary', 'Express', 'Limited Stop',
                               'Night Service', 'Electric (AC)', 'Feeder')),
    origin                  VARCHAR(100)  NOT NULL,
    destination             VARCHAR(100)  NOT NULL,
    total_distance_km       NUMERIC(6,1)  NOT NULL CHECK (total_distance_km > 0),
    scheduled_duration_min  INTEGER       NOT NULL CHECK (scheduled_duration_min > 0),
    active_status           BOOLEAN       NOT NULL DEFAULT TRUE,
    source_ref              VARCHAR(10)   NOT NULL
);

-- -----------------------------------------------------------------------------
-- stops — real Chennai localities
-- -----------------------------------------------------------------------------
CREATE TABLE stops (
    stop_id     VARCHAR(10)   PRIMARY KEY,
    stop_name   VARCHAR(100)  NOT NULL,
    latitude    NUMERIC(9,6)  NOT NULL CHECK (latitude BETWEEN -90 AND 90),
    longitude   NUMERIC(9,6)  NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    zone        VARCHAR(100)  NOT NULL,
    -- Chennai metropolitan bounding box sanity check (approximate)
    CHECK (latitude BETWEEN 12.6 AND 13.3 AND longitude BETWEEN 79.9 AND 80.4)
);

-- -----------------------------------------------------------------------------
-- route_stops — junction table preserving stop order along each route
-- -----------------------------------------------------------------------------
CREATE TABLE route_stops (
    route_id                  VARCHAR(10)   NOT NULL REFERENCES routes(route_id),
    stop_id                   VARCHAR(10)   NOT NULL REFERENCES stops(stop_id),
    stop_sequence              INTEGER       NOT NULL CHECK (stop_sequence > 0),
    distance_from_origin_km   NUMERIC(6,1)  NOT NULL CHECK (distance_from_origin_km >= 0),
    PRIMARY KEY (route_id, stop_sequence),
    UNIQUE (route_id, stop_id)
);

-- -----------------------------------------------------------------------------
-- buses — synthetic fleet, calibrated to real MTC fleet composition
-- -----------------------------------------------------------------------------
CREATE TABLE buses (
    bus_id                 VARCHAR(10)   PRIMARY KEY,
    capacity               INTEGER       NOT NULL CHECK (capacity > 0),
    bus_type               VARCHAR(30)   NOT NULL
        CHECK (bus_type IN ('Standard', 'Mini Bus', 'AC Electric')),
    operating_cost_per_km  NUMERIC(6,2)  NOT NULL CHECK (operating_cost_per_km > 0),
    active_status          BOOLEAN       NOT NULL DEFAULT TRUE
);

-- -----------------------------------------------------------------------------
-- trips — synthetic, calibrated (scheduled per route headway template,
-- actual times include injected delay)
-- -----------------------------------------------------------------------------
CREATE TABLE trips (
    trip_id              VARCHAR(15)  PRIMARY KEY,
    route_id             VARCHAR(10)  NOT NULL REFERENCES routes(route_id),
    bus_id               VARCHAR(10)  NOT NULL REFERENCES buses(bus_id),
    service_date         DATE         NOT NULL,
    scheduled_departure  TIMESTAMP    NOT NULL,
    actual_departure     TIMESTAMP    NOT NULL,
    scheduled_arrival    TIMESTAMP    NOT NULL,
    actual_arrival       TIMESTAMP    NOT NULL,
    CHECK (actual_arrival >= actual_departure),
    CHECK (scheduled_arrival >= scheduled_departure)
);

-- -----------------------------------------------------------------------------
-- passenger_counts — synthetic, calibrated to real crowding benchmarks
-- -----------------------------------------------------------------------------
CREATE TABLE passenger_counts (
    trip_id           VARCHAR(15)  NOT NULL REFERENCES trips(trip_id),
    stop_id           VARCHAR(10)  NOT NULL REFERENCES stops(stop_id),
    "timestamp"       TIMESTAMP    NOT NULL,
    boardings         INTEGER      NOT NULL CHECK (boardings >= 0),
    alightings        INTEGER      NOT NULL CHECK (alightings >= 0),
    passenger_count   INTEGER      NOT NULL CHECK (passenger_count >= 0),
    PRIMARY KEY (trip_id, stop_id)
);

-- -----------------------------------------------------------------------------
-- Indexes to support the analysis queries in sql/02–06
-- -----------------------------------------------------------------------------
CREATE INDEX idx_route_stops_route ON route_stops(route_id);
CREATE INDEX idx_trips_route_date ON trips(route_id, service_date);
CREATE INDEX idx_trips_bus ON trips(bus_id);
CREATE INDEX idx_passenger_counts_trip ON passenger_counts(trip_id);
CREATE INDEX idx_passenger_counts_stop ON passenger_counts(stop_id);
