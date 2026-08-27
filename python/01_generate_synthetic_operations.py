"""
01_generate_synthetic_operations.py

Purpose: Generate the three calibrated-synthetic operational tables
         (buses, trips, passenger_counts) that sit on top of the real
         routes / stops / route_stops geography built by
         00_build_real_route_stop_data.py.

No open MTC dataset exists at trip or boarding/alighting granularity
(see docs/assumptions.md), so these tables are generated from documented
transit-planning methodology and public MTC scale/crowding benchmarks,
NOT presented as real measurements. Every calibration choice below is
commented with its rationale so it can be audited or challenged.

Phase: 1 (Data Acquisition & Database Design)

------------------------------------------------------------------------------
CALIBRATION METHODOLOGY (see docs/assumptions.md for the full writeup)
------------------------------------------------------------------------------
1. buses
   - bus_type is assigned per route_type using the same mapping used to
     build the real route data (Standard / Mini Bus / AC Electric), so a
     route's real documented service tier drives its fleet composition.
   - capacity is sampled per bus_type from ranges grounded in typical
     Indian city-bus norms (Standard ~60-80 seated+standing; Mini Bus
     ~30-40; AC Electric low-floor ~50-65) — see assumptions.md.
   - Fleet SIZE is not a naive scaled-down copy of the real ~3,376-bus
     citywide fleet (that figure covers MTC's real ~650+ route network,
     not this project's 47-route sample). Instead, each route is assigned
     the number of buses actually required to sustain its own peak-hour
     headway — round_trip_time / peak_headway, rounded up — plus a
     documented spare/maintenance ratio. This is the same method real
     transit planners use, so per-route bus-to-frequency ratios stay
     realistic even though the total fleet count reflects a 47-route
     subset, not the citywide total.
   - operating_cost_per_km is an illustrative estimate per assumptions.md
     rule #4, not an accounting figure.

2. trips
   - Each route runs a full daily schedule (05:00-23:00, or the overnight
     window for the one Night Service route) built from a headway
     template: tighter headway in the two documented peak windows
     (07:00-10:00, 17:00-20:00), looser off-peak, calibrated per
     route_type (Ordinary/Feeder run more frequently than Express/AC).
   - actual_departure/actual_arrival apply an injected delay drawn from a
     right-skewed (gamma) distribution — heavier and more variable delay
     for Ordinary/Feeder (more stops, more mixed traffic), tighter for
     Express/Electric (AC) — with a small weekday/weekend traffic
     reduction, consistent with documented general urban traffic patterns.

3. passenger_counts
   - Boardings/alightings per stop follow a load-profile curve (near-zero
     at the terminus, peak around the route's midpoint) — standard
     transit-planning "max load point" modeling — with Poisson noise
     layered on top so counts aren't suspiciously smooth.
   - The curve's peak height is calibrated per trip via a target
     peak-occupancy ratio (peak load ÷ assigned bus capacity), sampled
     per route_type and peak/off-peak from documented parameters. Ordinary
     routes at peak are calibrated to a mean ratio > 1.0 (i.e., over
     nominal capacity), consistent with the real, sourced MTC overcrowding
     benchmark in docs/assumptions.md. Other tiers/off-peak land well
     under capacity.
   - Weekend ridership (all routes) is scaled down (Sat 0.85x, Sun 0.65x),
     consistent with reduced weekday-commute demand — supports the
     weekday-vs-weekend business question in docs/business_requirements.md.
------------------------------------------------------------------------------
"""

import csv
import math
import os
from datetime import date, datetime, timedelta

import numpy as np


def round_to_second(dt):
    """Drop sub-second noise so timestamps read cleanly in CSV/Postgres."""
    return dt.replace(microsecond=0) + timedelta(seconds=round(dt.microsecond / 1_000_000))

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
RANDOM_SEED = 42
rng = np.random.default_rng(RANDOM_SEED)

START_DATE = date(2026, 7, 1)
NUM_DAYS = 30  # one simulated month of operations

PEAK_WINDOWS = [(7, 0, 10, 0), (17, 0, 20, 0)]  # (start_h, start_m, end_h, end_m)

# route_type -> (peak_headway_min, offpeak_headway_min)
HEADWAY_MIN = {
    "Ordinary": (12, 25),
    "Limited Stop": (18, 35),
    "Feeder": (15, 28),
    "Express": (25, 50),
    "Electric (AC)": (22, 45),
    "Night Service": (50, 50),  # single overnight headway, no peak/off-peak split
}

# route_type -> bus_type (same mapping used in 00_build_real_route_stop_data.py)
BUS_TYPE_BY_ROUTE_TYPE = {
    "Ordinary": "Standard",
    "Express": "Standard",
    "Limited Stop": "Standard",
    "Night Service": "Standard",
    "Electric (AC)": "AC Electric",
    "Feeder": "Mini Bus",
}

# bus_type -> (capacity_min, capacity_max), (cost_per_km_min, cost_per_km_max)
BUS_TYPE_PARAMS = {
    "Standard": {"capacity": (60, 80), "cost_per_km": (55.0, 65.0)},
    "Mini Bus": {"capacity": (30, 40), "cost_per_km": (35.0, 45.0)},
    "AC Electric": {"capacity": (50, 65), "cost_per_km": (45.0, 55.0)},
}

SPARE_RATIO = 0.20  # documented maintenance/spare-fleet buffer
BUS_DOWN_FRACTION = 0.05  # small fraction of fleet inactive at any time

# route_type -> expected extra running delay, in minutes per km
DELAY_RATE_PER_KM = {
    "Ordinary": 0.25,
    "Limited Stop": 0.15,
    "Feeder": 0.10,
    "Express": 0.08,
    "Electric (AC)": 0.05,
    "Night Service": 0.05,
}

# route_type -> (departure delay gamma shape, scale) in minutes
DEPARTURE_DELAY_PARAMS = {
    "Ordinary": (2.0, 3.0),
    "Limited Stop": (1.8, 2.5),
    "Feeder": (1.5, 2.0),
    "Express": (1.2, 1.5),
    "Electric (AC)": (1.0, 1.2),
    "Night Service": (1.0, 1.0),
}

# (route_type, is_peak) -> (mean occupancy ratio, std)
PEAK_LOAD_RATIO_PARAMS = {
    ("Ordinary", True): (1.15, 0.20),
    ("Ordinary", False): (0.55, 0.15),
    ("Limited Stop", True): (1.05, 0.15),
    ("Limited Stop", False): (0.45, 0.10),
    ("Feeder", True): (0.85, 0.20),
    ("Feeder", False): (0.35, 0.10),
    ("Express", True): (0.75, 0.15),
    ("Express", False): (0.30, 0.10),
    ("Electric (AC)", True): (0.65, 0.15),
    ("Electric (AC)", False): (0.30, 0.10),
    ("Night Service", True): (0.40, 0.15),
    ("Night Service", False): (0.25, 0.10),
}

WEEKEND_DEMAND_MULTIPLIER = {5: 0.85, 6: 0.65}  # Mon=0,...,Sat=5,Sun=6


# ---------------------------------------------------------------------------
# Load real data
# ---------------------------------------------------------------------------
def load_csv(name):
    path = os.path.join(RAW_DIR, name)
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


routes = load_csv("routes.csv")
route_stops = load_csv("route_stops.csv")

routes_by_id = {r["route_id"]: r for r in routes}

stops_by_route = {}
for rs in route_stops:
    stops_by_route.setdefault(rs["route_id"], []).append(rs)
for rid in stops_by_route:
    stops_by_route[rid].sort(key=lambda x: int(x["stop_sequence"]))


def in_peak(t):
    for sh, sm, eh, em in PEAK_WINDOWS:
        start = sh * 60 + sm
        end = eh * 60 + em
        cur = t.hour * 60 + t.minute
        if start <= cur < end:
            return True
    return False


# ---------------------------------------------------------------------------
# 1. Generate buses
# ---------------------------------------------------------------------------
buses_rows = []
bus_pool_by_route = {}
bus_counter = 0


def new_bus(bus_type):
    global bus_counter
    bus_counter += 1
    bus_id = f"B{bus_counter:04d}"
    cap_lo, cap_hi = BUS_TYPE_PARAMS[bus_type]["capacity"]
    cost_lo, cost_hi = BUS_TYPE_PARAMS[bus_type]["cost_per_km"]
    capacity = int(rng.integers(cap_lo, cap_hi + 1))
    cost_per_km = round(float(rng.uniform(cost_lo, cost_hi)), 2)
    active = bool(rng.random() > BUS_DOWN_FRACTION)
    buses_rows.append(
        {
            "bus_id": bus_id,
            "capacity": capacity,
            "bus_type": bus_type,
            "operating_cost_per_km": cost_per_km,
            "active_status": active,
        }
    )
    return bus_id


for route in routes:
    rid = route["route_id"]
    rtype = route["route_type"]
    distance_km = float(route["total_distance_km"])
    duration_min = int(route["scheduled_duration_min"])
    round_trip_min = duration_min * 2

    peak_headway, offpeak_headway = HEADWAY_MIN[rtype]
    tightest_headway = min(peak_headway, offpeak_headway)

    buses_needed = math.ceil(round_trip_min / tightest_headway)
    buses_needed = max(1, buses_needed)
    fleet_size = max(buses_needed + 1, math.ceil(buses_needed * (1 + SPARE_RATIO)))

    bus_type = BUS_TYPE_BY_ROUTE_TYPE[rtype]
    pool = [new_bus(bus_type) for _ in range(fleet_size)]
    bus_pool_by_route[rid] = pool

print(f"buses.csv: {len(buses_rows)} buses across {len(routes)} routes")


# ---------------------------------------------------------------------------
# 2. Generate trips
# ---------------------------------------------------------------------------
trips_rows = []
# trip_id -> extra context needed for passenger_counts generation
trip_context = {}

for route in routes:
    rid = route["route_id"]
    rtype = route["route_type"]
    distance_km = float(route["total_distance_km"])
    duration_min = int(route["scheduled_duration_min"])
    peak_headway, offpeak_headway = HEADWAY_MIN[rtype]
    pool = bus_pool_by_route[rid]
    dep_shape, dep_scale = DEPARTURE_DELAY_PARAMS[rtype]
    delay_rate = DELAY_RATE_PER_KM[rtype]

    for day_offset in range(NUM_DAYS):
        service_date = START_DATE + timedelta(days=day_offset)
        weekday = service_date.weekday()
        weekend_mult = WEEKEND_DEMAND_MULTIPLIER.get(weekday, 1.0)

        if rtype == "Night Service":
            service_start = datetime.combine(service_date, datetime.min.time()) + timedelta(hours=23)
            service_end = service_start + timedelta(hours=6)
        else:
            service_start = datetime.combine(service_date, datetime.min.time()) + timedelta(hours=5)
            service_end = datetime.combine(service_date, datetime.min.time()) + timedelta(hours=23)

        cursor = service_start
        seq = 0
        while cursor < service_end:
            seq += 1
            is_peak = in_peak(cursor) if rtype != "Night Service" else False
            headway = peak_headway if is_peak else offpeak_headway

            scheduled_departure = cursor
            scheduled_arrival = scheduled_departure + timedelta(minutes=duration_min)

            # --- delay injection ---
            traffic_mult = 0.7 if weekday >= 5 else 1.0  # lighter weekend traffic
            dep_delay = rng.gamma(dep_shape, dep_scale) * traffic_mult - 1.0
            dep_delay = max(dep_delay, -2.0)
            actual_departure = round_to_second(scheduled_departure + timedelta(minutes=float(dep_delay)))

            expected_extra = delay_rate * distance_km * traffic_mult
            extra_delay = rng.gamma(2.0, max(expected_extra / 2.0, 0.1))
            actual_arrival = round_to_second(
                actual_departure + timedelta(minutes=duration_min + float(extra_delay))
            )

            bus_id = pool[(seq - 1) % len(pool)]
            trip_id = f"{rid}{service_date.strftime('%y%m%d')}{seq:03d}"

            trips_rows.append(
                {
                    "trip_id": trip_id,
                    "route_id": rid,
                    "bus_id": bus_id,
                    "service_date": service_date.isoformat(),
                    "scheduled_departure": scheduled_departure.isoformat(sep=" "),
                    "actual_departure": actual_departure.isoformat(sep=" "),
                    "scheduled_arrival": scheduled_arrival.isoformat(sep=" "),
                    "actual_arrival": actual_arrival.isoformat(sep=" "),
                }
            )

            trip_context[trip_id] = {
                "route_id": rid,
                "route_type": rtype,
                "bus_id": bus_id,
                "is_peak": is_peak,
                "weekend_mult": weekend_mult,
                "actual_departure": actual_departure,
                "actual_arrival": actual_arrival,
            }

            cursor += timedelta(minutes=headway)

print(f"trips.csv: {len(trips_rows)} trips across {NUM_DAYS} days")


# ---------------------------------------------------------------------------
# 3. Generate passenger_counts
# ---------------------------------------------------------------------------
bus_capacity_by_id = {b["bus_id"]: b["capacity"] for b in buses_rows}
passenger_rows = []

for trip in trips_rows:
    trip_id = trip["trip_id"]
    ctx = trip_context[trip_id]
    rid = ctx["route_id"]
    rtype = ctx["route_type"]
    stops_seq = stops_by_route[rid]
    n = len(stops_seq)
    if n < 2:
        continue  # cannot model boarding/alighting on a single-stop "route"

    capacity = bus_capacity_by_id[ctx["bus_id"]]
    mean_ratio, std_ratio = PEAK_LOAD_RATIO_PARAMS[(rtype, ctx["is_peak"])]
    target_ratio = float(rng.normal(mean_ratio, std_ratio)) * ctx["weekend_mult"]
    target_ratio = max(0.10, min(target_ratio, 1.60))
    max_load = max(2, round(target_ratio * capacity))

    # Load-profile "hump" shape: modest at origin, peak near midpoint,
    # forced to zero at the terminus (standard max-load-point modeling).
    shape = [math.sin(math.pi * (k + 0.5) / n) for k in range(n)]
    raw_target = [max_load * s for s in shape]
    raw_target[-1] = 0.0

    total_km = float(routes_by_id[rid]["total_distance_km"])
    dep_time = ctx["actual_departure"]
    arr_time = ctx["actual_arrival"]
    trip_span = (arr_time - dep_time).total_seconds()

    onboard = 0
    for k, rs in enumerate(stops_seq):
        stop_id = rs["stop_id"]
        dist_from_origin = float(rs["distance_from_origin_km"])
        frac = (dist_from_origin / total_km) if total_km > 0 else (k / (n - 1))
        frac = min(max(frac, 0.0), 1.0)
        ts = round_to_second(dep_time + timedelta(seconds=frac * trip_span))

        if k == n - 1:
            alight = onboard
            board = 0
        elif k == 0:
            board = max(0, round(raw_target[k]) + int(rng.poisson(1)))
            alight = 0
        else:
            desired = raw_target[k]
            delta = desired - onboard
            churn = max(1, round(0.05 * onboard)) if onboard > 0 else 0
            if delta >= 0:
                alight = churn
                board = churn + int(round(delta)) + int(rng.poisson(1))
            else:
                alight = churn + int(round(-delta))
                board = int(rng.poisson(1))
            alight = min(alight, onboard)

        onboard = max(0, onboard - alight + board)

        passenger_rows.append(
            {
                "trip_id": trip_id,
                "stop_id": stop_id,
                "timestamp": ts.isoformat(sep=" "),
                "boardings": board,
                "alightings": alight,
                "passenger_count": onboard,
            }
        )

print(f"passenger_counts.csv: {len(passenger_rows)} stop-level records")


# ---------------------------------------------------------------------------
# Write CSVs
# ---------------------------------------------------------------------------
def write_csv(name, rows):
    path = os.path.join(RAW_DIR, name)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


write_csv("buses.csv", buses_rows)
write_csv("trips.csv", trips_rows)
write_csv("passenger_counts.csv", passenger_rows)

print("\nDone. Wrote buses.csv, trips.csv, passenger_counts.csv to data/raw/")
