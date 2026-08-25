# Data Dictionary

Status legend: **Real** = derived from real Chennai geography/public data · **Synthetic (calibrated)** = generated but tuned to match real benchmark ranges · **Synthetic** = generated with no real-world anchor · **Derived** = computed from other fields.

## routes

| Field | Type | Description | Status | Notes |
|---|---|---|---|---|
| route_id | string | Unique route identifier | Real | Primary key |
| route_name | string | Human-readable route name (e.g., corridor/termini) | Real | Based on known MTC corridors |
| route_type | string | Local / Express / Feeder | Synthetic (calibrated) | Assigned per known route character |
| total_distance_km | float | Route distance | Real | Approximated from corridor geography |
| scheduled_duration_min | int | Expected journey duration | Synthetic (calibrated) | Derived from distance + assumed avg speed |
| active_status | boolean | Whether route is active | Synthetic | All active in v1 |

## stops

| Field | Type | Description | Status | Notes |
|---|---|---|---|---|
| stop_id | string | Unique stop identifier | Real | Primary key |
| stop_name | string | Stop name | Real | Known Chennai stop/locality names |
| latitude | float | Geographic latitude | Real | Must fall within Chennai bounding box |
| longitude | float | Geographic longitude | Real | Must fall within Chennai bounding box |
| zone | string | Geographic/administrative zone | Real | Chennai zone/area name |

## route_stops

| Field | Type | Description | Status | Notes |
|---|---|---|---|---|
| route_id | string | Route identifier | Real | FK → routes |
| stop_id | string | Stop identifier | Real | FK → stops |
| stop_sequence | int | Position in route | Real | Order along corridor |
| distance_from_origin_km | float | Distance from first stop | Derived | Cumulative from stop geography |

## buses

| Field | Type | Description | Status | Notes |
|---|---|---|---|---|
| bus_id | string | Unique bus identifier | Synthetic | Primary key |
| capacity | int | Max passenger capacity | Synthetic (calibrated) | Standard ~60–80, per MTC bus-type norms |
| bus_type | string | Standard / Articulated / Mini | Synthetic (calibrated) | Distribution matches typical MTC fleet mix |
| operating_cost_per_km | float | Approximate operating cost | Synthetic (calibrated) | Illustrative, not an accounting figure |
| active_status | boolean | Current availability | Synthetic | |

## trips

| Field | Type | Description | Status | Notes |
|---|---|---|---|---|
| trip_id | string | Unique trip identifier | Synthetic | Primary key |
| route_id | string | Route | Real | FK → routes |
| bus_id | string | Bus | Synthetic | FK → buses |
| service_date | date | Date | Synthetic | |
| scheduled_departure | timestamp | Scheduled departure | Synthetic (calibrated) | Per route headway template |
| actual_departure | timestamp | Actual departure | Synthetic (calibrated) | Scheduled + injected variance |
| scheduled_arrival | timestamp | Scheduled arrival | Synthetic (calibrated) | |
| actual_arrival | timestamp | Actual arrival | Synthetic (calibrated) | Used for delay calculation |

## passenger_counts

| Field | Type | Description | Status | Notes |
|---|---|---|---|---|
| trip_id | string | Trip | Synthetic | FK → trips |
| stop_id | string | Stop | Real | FK → stops |
| timestamp | timestamp | Observation time | Synthetic | |
| boardings | int | Number boarding | Synthetic (calibrated) | Non-negative; tuned to peak/off-peak curve |
| alightings | int | Number leaving | Synthetic (calibrated) | Non-negative |
| passenger_count | int | Estimated onboard passengers | Derived | Running total from boardings/alightings |

## weather (optional, later phase)

| Field | Type | Description | Status | Notes |
|---|---|---|---|---|
| timestamp | timestamp | Observation time | Synthetic | |
| temperature | float | Temperature | Synthetic | Loosely modeled on Chennai seasonal norms |
| rainfall_mm | float | Rainfall | Synthetic | Monsoon-season weighting |
| humidity | float | Humidity | Synthetic | |
| weather_condition | string | Weather category | Synthetic | |

## incidents (optional, later phase)

| Field | Type | Description | Status | Notes |
|---|---|---|---|---|
| incident_id | string | Unique incident | Synthetic | Primary key |
| timestamp | timestamp | Incident time | Synthetic | |
| latitude / longitude | float | Location | Synthetic | Constrained to Chennai bounding box |
| incident_type | string | Accident / Roadwork / Congestion | Synthetic | |
| severity | string | Severity level | Synthetic | |

---

_This dictionary is the canonical field-level reference. See [`../docs/assumptions.md`](../docs/assumptions.md) for the sourcing/calibration methodology behind the "Status" column._
