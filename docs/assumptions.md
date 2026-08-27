# Data Sourcing & Assumptions

Transparency about what is real, what is synthetic, and why, is treated as a core deliverable of this project — not an afterthought.

## Why Not Raw MTC GTFS

MTC Chennai has published GTFS feeds in the past, archived on Transitland and GTFS Data Exchange. On inspection (per community reports), these archives are outdated (last known good version ~2010–2017) and inconsistent — route/stop coordinates in at least one archived copy do not reliably correspond to real Chennai locations. Building the schema directly on this feed would risk quietly encoding bad geography. It is therefore used only as background reference, not as a direct data source.

## What Is Real

- **Route corridors, major stops, and termini**: based on publicly known MTC route structure and Chennai geography (e.g., Broadway, Koyambedu/CMBT, T. Nagar, and other well-documented hubs), cross-referenced against OpenStreetMap's Chennai bus-route mapping data.
- **Fleet and ridership scale benchmarks** (used to calibrate synthetic data, not injected as row-level records): approximate fleet size (~3,300+ buses), number of routes (~650+), and daily ridership (~5 million), plus documented crowding levels (peak occupancy materially above nominal capacity on busy routes) — sourced from public MTC reporting and Wikipedia, and from the Chennai MTC Performance Data series (2020–21 to 2024–25) published on opencity.in.

## What Is Synthetic (and Why)

- **Trip-level records** (`trips`): no open trip-level MTC dataset exists. Departure/arrival times are generated on a schedule template per route type, with randomized delay injected.
- **Passenger counts** (`passenger_counts`): no open boarding/alighting dataset exists at stop level. Generated per trip/stop using a demand curve (peak/off-peak weighting) calibrated so that route-level aggregates land within the real benchmark ranges above (e.g., known crowded routes should show peak occupancy > 100%, consistent with reported real-world crowding).
- **Weather / incidents** (if used): synthetic, loosely modeled on typical Chennai seasonal patterns (monsoon rainfall spikes), not tied to specific recorded events.

**No synthetic value is presented as an actual measurement.** Every generation script documents its method and parameters; every dataset file states in `data/data_dictionary.md` whether a field is real, synthetic, or derived.

## Analytical Assumptions

1. A trip is considered on time if it arrives no more than 5 minutes after its scheduled arrival.
2. Bus capacity is based on recorded nominal seated + standing capacity for the bus type.
3. Estimated waiting time is approximated as headway / 2 when direct passenger-arrival timestamps are unavailable (true here, since all passenger arrival data is synthetic).
4. Operating cost is an illustrative estimate (distance × cost-per-km), not an accounting figure.
5. Correlation identified in the analysis (e.g., weather vs. delay) does not establish causation.
6. Scenario/what-if outputs (later phase) represent estimates under stated assumptions, not guaranteed real-world outcomes.

## Data Quality Rules Applied

- Passenger counts must be non-negative.
- Bus capacity must be > 0.
- Latitude ∈ [-90, 90], longitude ∈ [-180, 180], and must fall within the Chennai metropolitan bounding box.
- Actual arrival must not precede actual departure.
- Occupancy exceeding physically plausible limits is flagged for review rather than silently accepted.

## Synthetic Operations Generator — Finalized Methodology (Phase 1)

`python/01_generate_synthetic_operations.py` produces `buses.csv`, `trips.csv`,
and `passenger_counts.csv` on top of the real route/stop geography. Full
parameter tables live as commented config at the top of the script; summary:

- **Fleet size is not a scaled-down copy of the real ~3,376-bus citywide
  fleet** — that figure covers MTC's real ~650+ route network, not this
  project's 47-route sample, so naively scaling it down would misrepresent
  both numbers. Instead, each route is assigned the number of buses actually
  required to sustain its own peak headway (`round_trip_time ÷ tightest
  headway`, rounded up) plus a 20% spare/maintenance buffer — the same
  method real transit planners use. This keeps per-route bus-to-frequency
  ratios realistic even though the total fleet count (currently 556 buses)
  reflects a 47-route subset, not the citywide total.
- **Trips** follow a headway template per route_type (tighter in the two
  documented peak windows, 07:00–10:00 and 17:00–20:00) with a right-skewed
  (gamma) delay injected on top — heavier/more variable for Ordinary and
  Feeder routes, tighter for Express/Electric (AC), with a documented 30%
  weekend traffic reduction.
- **Passenger counts** follow a load-profile curve (near-zero at the
  terminus, peaking near the route's midpoint — standard "max load point"
  transit-planning modeling) with Poisson noise layered on. The peak height
  is calibrated per trip via a target occupancy ratio sampled per
  route_type/peak-off-peak; Ordinary and Limited Stop routes at peak are
  calibrated to land **above 100% of bus capacity**, consistent with the
  real, sourced MTC overcrowding benchmark above. Weekend ridership is
  scaled down (Sat 0.85×, Sun 0.65×) to support the weekday-vs-weekend
  business question in `docs/business_requirements.md`.
- Simulated period: 30 days (2026-07-01 to 2026-07-30). This is a
  synthetic operating window, not a claim about actual conditions in that
  period.
- Fully reproducible: fixed random seed (42) via `numpy.random.default_rng`.

_This file will be updated as data generation scripts are finalized in Phase 1._
