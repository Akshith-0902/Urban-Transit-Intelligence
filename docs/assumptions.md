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

_This file will be updated as data generation scripts are finalized in Phase 1._
