"""
01_data_cleaning.py

Purpose: Connect to the loaded Postgres database, run the same category of
         checks as sql/01_data_validation.sql (completeness, validity,
         consistency, uniqueness, plausibility), and produce a structured,
         auditable data quality report — the evidence that Phase 3+ analysis
         is built on trustworthy data.
Phase:   2 (Data Cleaning & Validation)
Status:  DONE

Design note
-----------
00_schema.sql already enforces NOT NULL / CHECK / PRIMARY KEY / FOREIGN KEY
constraints at the database level, so completeness, validity, and uniqueness
checks are expected to return 0 violations here — Postgres would have
rejected the offending row on load. They're still run and reported (each
flagged `schema_enforced=True`) so this script is a real, repeatable audit
rather than an assumption. The checks expected to actually surface findings
are the cross-row consistency checks (bus double-booking, running passenger
balance, stop-sequence gaps) and the plausibility check (occupancy ceiling),
because those encode logic a single-column CHECK constraint can't express.

This script does not delete or silently alter any data. It only detects and
reports. If real dirty data is ever found, fix it at the source (regenerate
via 01_generate_synthetic_operations.py) rather than patching it here, to
keep the raw -> processed lineage honest.

Usage
-----
    1. Copy .env.example to .env and fill in your local Postgres credentials.
    2. python python/01_data_cleaning.py

Outputs
-------
    data/processed/data_quality_report.csv   (structured, one row per check)
    reports/data_quality_report.md           (human-readable narrative)
"""

import os
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, URL

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
REPORTS_DIR = PROJECT_ROOT / "reports"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------
def get_engine() -> Engine:
    """Build a SQLAlchemy engine from .env variables."""
    load_dotenv(PROJECT_ROOT / ".env")

    required = ["DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD"]
    missing = [v for v in required if not os.getenv(v)]
    if missing:
        sys.exit(
            f"Missing required .env variable(s): {', '.join(missing)}.\n"
            f"Copy .env.example to .env in the project root and fill in "
            f"your local Postgres credentials."
        )

    # Use URL.create (not an f-string) so special characters in the password
    # (e.g. "@", ":", "/") are percent-encoded correctly instead of breaking
    # the connection string.
    url = URL.create(
        drivername="postgresql+psycopg2",
        username=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT")),
        database=os.getenv("DB_NAME"),
    )
    return create_engine(url)


# ---------------------------------------------------------------------------
# Check definitions
# Each check is (name, category, schema_enforced, sql, description)
# schema_enforced=True checks are expected to always return 0 violations on
# this database; they're run anyway as a genuine audit trail.
# ---------------------------------------------------------------------------
CHECKS = [
    (
        "null_route_fields",
        "Completeness",
        True,
        """
        SELECT COUNT(*) AS violations FROM routes
        WHERE route_number IS NULL OR route_name IS NULL OR route_type IS NULL
           OR origin IS NULL OR destination IS NULL OR total_distance_km IS NULL
        """,
        "Required route fields must not be NULL.",
    ),
    (
        "null_trip_fields",
        "Completeness",
        True,
        """
        SELECT COUNT(*) AS violations FROM trips
        WHERE route_id IS NULL OR bus_id IS NULL OR service_date IS NULL
           OR scheduled_departure IS NULL OR actual_departure IS NULL
           OR scheduled_arrival IS NULL OR actual_arrival IS NULL
        """,
        "Required trip fields must not be NULL.",
    ),
    (
        "null_passenger_count_fields",
        "Completeness",
        True,
        """
        SELECT COUNT(*) AS violations FROM passenger_counts
        WHERE trip_id IS NULL OR stop_id IS NULL OR "timestamp" IS NULL
           OR boardings IS NULL OR alightings IS NULL OR passenger_count IS NULL
        """,
        "Required passenger_counts fields must not be NULL.",
    ),
    (
        "negative_or_zero_values",
        "Validity",
        True,
        """
        SELECT
            (SELECT COUNT(*) FROM passenger_counts WHERE boardings < 0) +
            (SELECT COUNT(*) FROM passenger_counts WHERE alightings < 0) +
            (SELECT COUNT(*) FROM passenger_counts WHERE passenger_count < 0) +
            (SELECT COUNT(*) FROM buses WHERE capacity <= 0) +
            (SELECT COUNT(*) FROM routes WHERE total_distance_km <= 0) +
            (SELECT COUNT(*) FROM route_stops WHERE stop_sequence <= 0)
            AS violations
        """,
        "No negative boardings/alightings/passenger_count, and capacity, "
        "distance, and stop_sequence must be positive.",
    ),
    (
        "stops_outside_chennai_bbox",
        "Validity",
        True,
        """
        SELECT COUNT(*) AS violations FROM stops
        WHERE NOT (latitude BETWEEN 12.6 AND 13.3 AND longitude BETWEEN 79.9 AND 80.4)
        """,
        "Stop coordinates must fall within the Chennai metro bounding box.",
    ),
    (
        "arrival_before_departure",
        "Validity",
        True,
        """
        SELECT COUNT(*) AS violations FROM trips
        WHERE actual_arrival < actual_departure OR scheduled_arrival < scheduled_departure
        """,
        "A trip cannot arrive before it departs.",
    ),
    (
        "duplicate_trip_id",
        "Uniqueness",
        True,
        """
        SELECT COALESCE(SUM(cnt), 0) AS violations FROM (
            SELECT COUNT(*) AS cnt FROM trips GROUP BY trip_id HAVING COUNT(*) > 1
        ) sub
        """,
        "trip_id must be unique.",
    ),
    (
        "duplicate_route_stop_pair",
        "Uniqueness",
        True,
        """
        SELECT COALESCE(SUM(cnt), 0) AS violations FROM (
            SELECT COUNT(*) AS cnt FROM route_stops
            GROUP BY route_id, stop_id HAVING COUNT(*) > 1
        ) sub
        """,
        "(route_id, stop_id) must be unique within route_stops.",
    ),
    (
        "duplicate_route_number",
        "Uniqueness",
        False,
        """
        SELECT COALESCE(SUM(cnt), 0) AS violations FROM (
            SELECT COUNT(DISTINCT route_id) AS cnt FROM routes
            GROUP BY route_number HAVING COUNT(DISTINCT route_id) > 1
        ) sub
        """,
        "route_number is a business key and should map to exactly one "
        "route_id (not schema-enforced — routes has no UNIQUE on route_number).",
    ),
    (
        "orphaned_foreign_keys",
        "Consistency",
        True,
        """
        SELECT
            (SELECT COUNT(*) FROM route_stops rs LEFT JOIN routes r ON r.route_id = rs.route_id WHERE r.route_id IS NULL) +
            (SELECT COUNT(*) FROM route_stops rs LEFT JOIN stops s ON s.stop_id = rs.stop_id WHERE s.stop_id IS NULL) +
            (SELECT COUNT(*) FROM trips t LEFT JOIN buses b ON b.bus_id = t.bus_id WHERE b.bus_id IS NULL) +
            (SELECT COUNT(*) FROM trips t LEFT JOIN routes r ON r.route_id = t.route_id WHERE r.route_id IS NULL) +
            (SELECT COUNT(*) FROM passenger_counts pc LEFT JOIN trips t ON t.trip_id = pc.trip_id WHERE t.trip_id IS NULL)
            AS violations
        """,
        "No row may reference a parent key that doesn't exist "
        "(redundant with FKs here, but the check that matters against a raw CSV export).",
    ),
    (
        "bus_double_booking",
        "Consistency",
        False,
        """
        SELECT COUNT(*) AS violations FROM (
            SELECT t1.trip_id
            FROM trips t1
            JOIN trips t2
              ON t1.bus_id = t2.bus_id
             AND t1.service_date = t2.service_date
             AND t1.trip_id < t2.trip_id
            WHERE t1.actual_departure < t2.actual_arrival
              AND t2.actual_departure < t1.actual_arrival
        ) sub
        """,
        "A single bus cannot be on two overlapping trips at once.",
    ),
    (
        "route_stops_sequence_gaps",
        "Consistency",
        False,
        """
        SELECT COUNT(*) AS violations FROM (
            SELECT route_id
            FROM route_stops
            GROUP BY route_id
            HAVING COUNT(*) <> (MAX(stop_sequence) - MIN(stop_sequence) + 1)
        ) sub
        """,
        "stop_sequence should be contiguous (no gaps) within each route.",
    ),
    (
        "passenger_count_running_balance",
        "Consistency",
        False,
        """
        WITH ordered AS (
            SELECT pc.trip_id, pc.passenger_count, pc.boardings, pc.alightings,
                   LAG(pc.passenger_count) OVER (
                       PARTITION BY pc.trip_id ORDER BY rs.stop_sequence
                   ) AS prev_count
            FROM passenger_counts pc
            JOIN trips t        ON t.trip_id = pc.trip_id
            JOIN route_stops rs ON rs.route_id = t.route_id AND rs.stop_id = pc.stop_id
        )
        SELECT COUNT(*) AS violations FROM ordered
        WHERE passenger_count <> COALESCE(prev_count, 0) - alightings + boardings
        """,
        "passenger_count at each stop should equal prev_count - alightings + boardings.",
    ),
    (
        "trips_outside_operating_hours",
        "Consistency",
        False,
        """
        SELECT COUNT(*) AS violations
        FROM trips tr JOIN routes r ON r.route_id = tr.route_id
        WHERE r.route_type <> 'Night Service'
          AND (tr.scheduled_departure::time < TIME '05:00' OR tr.scheduled_departure::time > TIME '23:00')
        """,
        "Non-Night-Service trips should depart within the 05:00-23:00 window.",
    ),
    (
        "service_date_outside_window",
        "Consistency",
        False,
        """
        SELECT COUNT(*) AS violations FROM trips
        WHERE service_date NOT BETWEEN DATE '2026-07-01' AND DATE '2026-07-30'
        """,
        "service_date should fall within the documented 30-day simulation window.",
    ),
    (
        "occupancy_over_200pct",
        "Plausibility",
        False,
        """
        SELECT COUNT(*) AS violations
        FROM passenger_counts pc
        JOIN trips t ON t.trip_id = pc.trip_id
        JOIN buses b ON b.bus_id = t.bus_id
        WHERE pc.passenger_count::numeric / b.capacity > 2.0
        """,
        "Occupancy over 200% of rated capacity is flagged for review, "
        "per docs/assumptions.md (not treated as a hard error).",
    ),
]


def run_checks(engine: Engine) -> pd.DataFrame:
    """Run every check in CHECKS and collect results into a DataFrame."""
    rows = []
    with engine.connect() as conn:
        for name, category, schema_enforced, sql, description in CHECKS:
            try:
                result = conn.execute(text(sql)).scalar()
                violations = int(result) if result is not None else 0
                status = "PASS" if violations == 0 else "REVIEW"
                error = None
            except Exception as exc:  # noqa: BLE001
                violations = None
                status = "ERROR"
                error = str(exc)
            rows.append(
                {
                    "check_name": name,
                    "category": category,
                    "schema_enforced": schema_enforced,
                    "violations": violations,
                    "status": status,
                    "description": description,
                    "error": error,
                }
            )
    return pd.DataFrame(rows)


def get_row_counts(engine: Engine) -> pd.DataFrame:
    tables = ["routes", "stops", "route_stops", "buses", "trips", "passenger_counts"]
    counts = []
    with engine.connect() as conn:
        for t in tables:
            n = conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
            counts.append({"table": t, "row_count": n})
    return pd.DataFrame(counts)


def get_calibration_summary(engine: Engine) -> dict:
    """Informational (not pass/fail) — confirms the generator hit its targets."""
    with engine.connect() as conn:
        total_buses = conn.execute(text("SELECT COUNT(*) FROM buses")).scalar()
        pct_on_time = conn.execute(
            text(
                """
                SELECT ROUND(100.0 * COUNT(*) FILTER (
                    WHERE actual_arrival <= scheduled_arrival + INTERVAL '5 minutes'
                ) / COUNT(*), 1)
                FROM trips
                """
            )
        ).scalar()
    return {"total_buses": total_buses, "pct_on_time": float(pct_on_time)}


def write_report(results: pd.DataFrame, row_counts: pd.DataFrame, calibration: dict) -> None:
    # Structured CSV for downstream use / re-analysis
    csv_path = PROCESSED_DIR / "data_quality_report.csv"
    results.to_csv(csv_path, index=False)

    # Human-readable markdown narrative
    n_pass = (results["status"] == "PASS").sum()
    n_review = (results["status"] == "REVIEW").sum()
    n_error = (results["status"] == "ERROR").sum()

    lines = [
        "# Data Quality Report — Phase 2",
        "",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## Summary",
        "",
        f"- Checks run: {len(results)}",
        f"- Pass: {n_pass}",
        f"- Flagged for review: {n_review}",
        f"- Errors: {n_error}",
        "",
        "## Row Counts",
        "",
        row_counts.to_markdown(index=False),
        "",
        "## Calibration Sanity Check (informational)",
        "",
        f"- Total buses: {calibration['total_buses']} (documented target: ~556)",
        f"- Overall on-time performance: {calibration['pct_on_time']}%",
        "",
        "## Check Results",
        "",
        "Checks marked `schema_enforced=True` are expected to always show 0 "
        "violations, since `00_schema.sql` already rejects the offending row "
        "at insert time (NOT NULL / CHECK / PRIMARY KEY / FOREIGN KEY). They "
        "are included as a genuine audit trail rather than an assumption. "
        "Findings, if any, are expected in the Consistency and Plausibility "
        "categories, which encode cross-row logic the schema can't express.",
        "",
        results[
            ["check_name", "category", "schema_enforced", "violations", "status", "description"]
        ].to_markdown(index=False),
        "",
    ]

    if n_review > 0:
        lines += [
            "## Flagged Items",
            "",
            "The following checks returned violations and should be reviewed "
            "before proceeding to Phase 3 analysis:",
            "",
        ]
        for _, row in results[results["status"] == "REVIEW"].iterrows():
            lines.append(f"- **{row['check_name']}** ({row['category']}): "
                          f"{row['violations']} violation(s) — {row['description']}")
        lines.append("")

    if n_error > 0:
        lines += [
            "## Errors",
            "",
            "The following checks could not run — see error detail below:",
            "",
        ]
        for _, row in results[results["status"] == "ERROR"].iterrows():
            lines.append(f"- **{row['check_name']}**: {row['error']}")
        lines.append("")

    report_path = REPORTS_DIR / "data_quality_report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")

    print(f"Wrote {csv_path}")
    print(f"Wrote {report_path}")
    print(f"\n{n_pass} passed, {n_review} flagged for review, {n_error} errored "
          f"out of {len(results)} checks.")


def main() -> None:
    engine = get_engine()
    print("Connected. Running data quality checks...")
    results = run_checks(engine)
    row_counts = get_row_counts(engine)
    calibration = get_calibration_summary(engine)
    write_report(results, row_counts, calibration)


if __name__ == "__main__":
    main()
