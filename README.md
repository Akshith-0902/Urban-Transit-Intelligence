# Urban Transit Intelligence
### Data-Driven Bus Capacity & Route Optimization — Chennai, India

[![Status](https://img.shields.io/badge/status-in%20progress-yellow)]()
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)]()
[![PostgreSQL](https://img.shields.io/badge/postgresql-15%2B-336791)]()
[![License](https://img.shields.io/badge/license-MIT-green)]()

## Overview

An end-to-end analytics and decision-support system built for a public transport authority (modeled on Chennai's MTC network) to answer one question:

> **How should a transport authority allocate its limited buses and service capacity to improve passenger experience while controlling operating costs?**

This is not a "download data → make charts → build dashboard" project. It follows a full analytics workflow — from raw operational data to root-cause analysis to evidence-backed, cost-aware recommendations — and is explicit about what's real data versus calibrated synthetic data (see [`docs/assumptions.md`](docs/assumptions.md)).

## The Business Problem

MTC Chennai operates one of the busiest bus networks in India — a large fleet running across hundreds of routes, with demand that swings sharply by time of day and route. Some routes run overcrowded at peak hours; others carry substantial unused capacity. Delays cluster on specific routes and stops. Management currently lacks a unified, data-driven view to guide bus allocation and frequency decisions.

This project builds that view: a relational data model, SQL/Python analysis layers, a KPI framework, an interactive Power BI dashboard, and (in a later phase) a what-if scenario simulator for evaluating allocation changes before committing to them.

## Analytical Workflow

```
Business Problem → Business Questions → Data Requirements → Data Collection
   → Data Cleaning & Validation → Database Design → SQL Analysis
   → Python Exploratory Analysis → Geospatial Analysis → KPI Development
   → Power BI Dashboard → Insights → Recommendations → Estimated Business Impact
```

## Data Approach

Real Chennai route/stop geography (major corridors and termini such as Broadway, Koyambedu/CMBT, T. Nagar, etc.) combined with synthetic operational data (trips, passenger counts, delays) calibrated against public MTC benchmarks (fleet size, ridership, known crowding levels). Full sourcing and calibration methodology documented in [`docs/assumptions.md`](docs/assumptions.md) and [`data/data_dictionary.md`](data/data_dictionary.md).

**No fabricated data is presented as real-world measurement.**

## Repository Structure

```
urban-transit-intelligence/
├── README.md
├── LICENSE
├── .gitignore
├── requirements.txt
│
├── data/
│   ├── raw/                    # Source data as obtained (real + generated)
│   ├── processed/              # Cleaned, analysis-ready datasets
│   └── data_dictionary.md      # Field-by-field documentation
│
├── sql/
│   ├── 01_data_validation.sql
│   ├── 02_demand_analysis.sql
│   ├── 03_route_performance.sql
│   ├── 04_capacity_analysis.sql
│   ├── 05_delay_analysis.sql
│   └── 06_advanced_analysis.sql
│
├── python/
│   ├── 01_data_cleaning.py
│   ├── 02_eda.py
│   ├── 03_geospatial_analysis.py
│   ├── 04_delay_analysis.py
│   └── 05_scenario_model.py
│
├── notebooks/
│   ├── 01_data_quality.ipynb
│   ├── 02_demand_analysis.ipynb
│   ├── 03_operational_analysis.ipynb
│   └── 04_geospatial_analysis.ipynb
│
├── powerbi/
│   └── urban_transit_dashboard.pbix
│
├── reports/
│   ├── executive_summary.md
│   └── methodology.md
│
└── docs/
    ├── business_requirements.md
    ├── data_dictionary.md
    └── assumptions.md
```

## Tech Stack

| Layer | Tools |
|---|---|
| Database | PostgreSQL |
| Analysis | Python (Pandas, NumPy, GeoPandas, Matplotlib, Plotly) |
| Dashboarding | Power BI |
| Version Control | Git / GitHub |
| Optional (later phases) | Scikit-learn, Statsmodels, Streamlit, optimization libraries |

## Project Status

This project is being built in phases, MVP first:

- [ ] Phase 0 — Foundations (repo, business requirements, KPI definitions)
- [ ] Phase 1 — Data acquisition & database design
- [ ] Phase 2 — Data cleaning & validation
- [ ] Phase 3 — SQL analytics
- [ ] Phase 4 — Python analysis (EDA, geospatial, delay investigation)
- [ ] Phase 5 — Power BI dashboard
- [ ] Phase 6 — Findings & recommendations
- [ ] Phase 7 (optional) — What-if scenario simulator
- [ ] Phase 8 (optional) — Weather/incident integration, forecasting, Streamlit app

See [`docs/business_requirements.md`](docs/business_requirements.md) for the full problem definition and [`reports/methodology.md`](reports/methodology.md) for how the analysis was conducted.

## Key Findings & Recommendations

_To be populated as analysis phases complete — see [`reports/executive_summary.md`](reports/executive_summary.md)._

## License

MIT — see [`LICENSE`](LICENSE).
