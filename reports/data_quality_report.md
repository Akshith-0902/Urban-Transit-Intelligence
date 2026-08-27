# Data Quality Report — Phase 2

Generated: 2026-08-28 01:56:55

## Summary

- Checks run: 16
- Pass: 16
- Flagged for review: 0
- Errors: 0

## Row Counts

| table            |   row_count |
|:-----------------|------------:|
| routes           |          47 |
| stops            |          70 |
| route_stops      |         181 |
| buses            |         556 |
| trips            |       71970 |
| passenger_counts |      281700 |

## Calibration Sanity Check (informational)

- Total buses: 556 (documented target: ~556)
- Overall on-time performance: 55.6%

## Check Results

Checks marked `schema_enforced=True` are expected to always show 0 violations, since `00_schema.sql` already rejects the offending row at insert time (NOT NULL / CHECK / PRIMARY KEY / FOREIGN KEY). They are included as a genuine audit trail rather than an assumption. Findings, if any, are expected in the Consistency and Plausibility categories, which encode cross-row logic the schema can't express.

| check_name                      | category     | schema_enforced   |   violations | status   | description                                                                                                                          |
|:--------------------------------|:-------------|:------------------|-------------:|:---------|:-------------------------------------------------------------------------------------------------------------------------------------|
| null_route_fields               | Completeness | True              |            0 | PASS     | Required route fields must not be NULL.                                                                                              |
| null_trip_fields                | Completeness | True              |            0 | PASS     | Required trip fields must not be NULL.                                                                                               |
| null_passenger_count_fields     | Completeness | True              |            0 | PASS     | Required passenger_counts fields must not be NULL.                                                                                   |
| negative_or_zero_values         | Validity     | True              |            0 | PASS     | No negative boardings/alightings/passenger_count, and capacity, distance, and stop_sequence must be positive.                        |
| stops_outside_chennai_bbox      | Validity     | True              |            0 | PASS     | Stop coordinates must fall within the Chennai metro bounding box.                                                                    |
| arrival_before_departure        | Validity     | True              |            0 | PASS     | A trip cannot arrive before it departs.                                                                                              |
| duplicate_trip_id               | Uniqueness   | True              |            0 | PASS     | trip_id must be unique.                                                                                                              |
| duplicate_route_stop_pair       | Uniqueness   | True              |            0 | PASS     | (route_id, stop_id) must be unique within route_stops.                                                                               |
| duplicate_route_number          | Uniqueness   | False             |            0 | PASS     | route_number is a business key and should map to exactly one route_id (not schema-enforced — routes has no UNIQUE on route_number).  |
| orphaned_foreign_keys           | Consistency  | True              |            0 | PASS     | No row may reference a parent key that doesn't exist (redundant with FKs here, but the check that matters against a raw CSV export). |
| bus_double_booking              | Consistency  | False             |            0 | PASS     | A single bus cannot be on two overlapping trips at once.                                                                             |
| route_stops_sequence_gaps       | Consistency  | False             |            0 | PASS     | stop_sequence should be contiguous (no gaps) within each route.                                                                      |
| passenger_count_running_balance | Consistency  | False             |            0 | PASS     | passenger_count at each stop should equal prev_count - alightings + boardings.                                                       |
| trips_outside_operating_hours   | Consistency  | False             |            0 | PASS     | Non-Night-Service trips should depart within the 05:00-23:00 window.                                                                 |
| service_date_outside_window     | Consistency  | False             |            0 | PASS     | service_date should fall within the documented 30-day simulation window.                                                             |
| occupancy_over_200pct           | Plausibility | False             |            0 | PASS     | Occupancy over 200% of rated capacity is flagged for review, per docs/assumptions.md (not treated as a hard error).                  |
