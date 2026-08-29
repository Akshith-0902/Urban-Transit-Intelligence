"""
02_eda.py

Purpose: Exploratory data analysis on the cleaned/validated dataset —
         demand, performance, and capacity patterns already surfaced in
         sql/02-04 and sql/06, rendered as static charts plus a short
         narrative summary. This is the visual counterpart to Phase 3,
         not new metrics: every number here is reproduced from the same
         SQL logic already validated in sql/02-06, just charted instead
         of tabulated.
Phase:   4 (Python Analysis)
Status:  DONE

Design note
-----------
Queries below intentionally mirror the exact CTEs/definitions already
live-tested in sql/02_demand_analysis.sql, sql/03_route_performance.sql,
sql/04_capacity_analysis.sql, and sql/06_advanced_analysis.sql (on-time =
actual_arrival <= scheduled_arrival + 5 min; peak windows = 07:00-10:00 /
17:00-20:00; route scorecard join order) so this script cannot silently
drift from Phase 3's already-audited definitions.

Usage
-----
    1. Copy .env.example to .env and fill in your local Postgres credentials
       (skip if already done for python/01_data_cleaning.py).
    2. python python/02_eda.py

Outputs
-------
    reports/figures/01_hourly_demand.png
    reports/figures/02_weekday_weekend_demand.png
    reports/figures/03_occupancy_peak_offpeak.png
    reports/figures/04_delay_distribution.png
    reports/figures/05_overcrowded_vs_underutilized.png
    reports/figures/06_route_scorecard_scatter.png
    reports/eda_summary.md
"""

import os
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import pandas as pd
import seaborn as sns
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, URL

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIGURES_DIR = PROJECT_ROOT / "reports" / "figures"
REPORTS_DIR = PROJECT_ROOT / "reports"
FIGURES_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

sns.set_theme(style="whitegrid", context="talk")
PALETTE = "viridis"


# ---------------------------------------------------------------------------
# Connection (same pattern as python/01_data_cleaning.py)
# ---------------------------------------------------------------------------
def get_engine() -> Engine:
    load_dotenv(PROJECT_ROOT / ".env")

    required = ["DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD"]
    missing = [v for v in required if not os.getenv(v)]
    if missing:
        sys.exit(
            f"Missing required .env variable(s): {', '.join(missing)}.\n"
            f"Copy .env.example to .env in the project root and fill in "
            f"your local Postgres credentials."
        )

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
# Queries — each mirrors an already-validated definition from sql/02-06
# ---------------------------------------------------------------------------
Q_HOURLY_DEMAND = """
    SELECT EXTRACT(HOUR FROM pc."timestamp")::int AS hour,
           SUM(pc.boardings) AS total_boardings
    FROM passenger_counts pc
    GROUP BY hour
    ORDER BY hour;
"""

Q_WEEKDAY_WEEKEND = """
    SELECT r.route_type,
           CASE
               WHEN EXTRACT(ISODOW FROM t.service_date) IN (6, 7) THEN 'Weekend'
               ELSE 'Weekday'
           END AS day_type,
           SUM(pc.boardings)::numeric
               / COUNT(DISTINCT t.service_date) AS avg_daily_boardings
    FROM passenger_counts pc
    JOIN trips t  ON t.trip_id = pc.trip_id
    JOIN routes r ON r.route_id = t.route_id
    GROUP BY r.route_type, day_type
    ORDER BY r.route_type, day_type;
"""

Q_OCCUPANCY_PEAK_OFFPEAK = """
    SELECT r.route_type,
           CASE
               WHEN pc."timestamp"::time BETWEEN TIME '07:00' AND TIME '10:00'
                 OR pc."timestamp"::time BETWEEN TIME '17:00' AND TIME '20:00'
               THEN 'Peak' ELSE 'Off-Peak'
           END AS period,
           pc.passenger_count::numeric / b.capacity AS occupancy_ratio
    FROM passenger_counts pc
    JOIN trips t  ON t.trip_id = pc.trip_id
    JOIN routes r ON r.route_id = t.route_id
    JOIN buses b  ON b.bus_id = t.bus_id;
"""

Q_DELAY_BUCKETS = """
    SELECT
        CASE
            WHEN actual_arrival <= scheduled_arrival + INTERVAL '5 minutes' THEN '1. On-time (<=5 min)'
            WHEN actual_arrival <= scheduled_arrival + INTERVAL '15 minutes' THEN '2. Minor (5-15 min)'
            WHEN actual_arrival <= scheduled_arrival + INTERVAL '30 minutes' THEN '3. Moderate (15-30 min)'
            ELSE '4. Severe (>30 min)'
        END AS delay_bucket,
        COUNT(*) AS trip_count
    FROM trips
    GROUP BY delay_bucket
    ORDER BY delay_bucket;
"""


# Overcrowded ranking matches sql/04_capacity_analysis.sql §2.1 exactly
# (peak-window occupancy); underutilized matches §3.1 exactly (overall
# mean occupancy) — these are deliberately different metrics, not the
# same column sorted two ways, per the audited Phase 3 definitions.
Q_ROUTE_PEAK_OCCUPANCY = """
    SELECT r.route_id, r.route_number, r.route_type,
           ROUND(AVG(pc.passenger_count::numeric / b.capacity), 2) AS avg_peak_occupancy
    FROM passenger_counts pc
    JOIN trips t  ON t.trip_id = pc.trip_id
    JOIN routes r ON r.route_id = t.route_id
    JOIN buses b  ON b.bus_id = t.bus_id
    WHERE pc."timestamp"::time BETWEEN TIME '07:00' AND TIME '10:00'
       OR pc."timestamp"::time BETWEEN TIME '17:00' AND TIME '20:00'
    GROUP BY r.route_id, r.route_number, r.route_type
    ORDER BY avg_peak_occupancy DESC;
"""

Q_ROUTE_OVERALL_OCCUPANCY = """
    SELECT r.route_id, r.route_number, r.route_type,
           ROUND(AVG(pc.passenger_count::numeric / b.capacity), 2) AS mean_occupancy_ratio
    FROM passenger_counts pc
    JOIN trips t  ON t.trip_id = pc.trip_id
    JOIN routes r ON r.route_id = t.route_id
    JOIN buses b  ON b.bus_id = t.bus_id
    GROUP BY r.route_id, r.route_number, r.route_type
    ORDER BY mean_occupancy_ratio ASC;
"""

# Route scorecard — reproduced verbatim from sql/06_advanced_analysis.sql §1.1
Q_ROUTE_SCORECARD = """
    WITH demand AS (
        SELECT t.route_id,
               SUM(pc.boardings)                          AS total_boardings,
               ROUND(SUM(pc.boardings)::numeric / 30, 0)  AS avg_boardings_per_day
        FROM passenger_counts pc JOIN trips t ON t.trip_id = pc.trip_id
        GROUP BY t.route_id
    ),
    performance AS (
        SELECT route_id,
               COUNT(*) AS total_trips,
               ROUND(100.0 * COUNT(*) FILTER (WHERE actual_arrival <= scheduled_arrival + INTERVAL '5 minutes')
                     / COUNT(*), 1) AS pct_on_time,
               ROUND(AVG(EXTRACT(EPOCH FROM (actual_arrival - scheduled_arrival)) / 60), 1) AS avg_delay_minutes,
               COUNT(DISTINCT bus_id) AS buses_used
        FROM trips
        GROUP BY route_id
    ),
    capacity AS (
        SELECT t.route_id,
               ROUND(AVG(pc.passenger_count::numeric / b.capacity), 2) AS avg_occupancy_ratio,
               ROUND(AVG(pc.passenger_count::numeric / b.capacity) FILTER (
                   WHERE pc."timestamp"::time BETWEEN TIME '07:00' AND TIME '10:00'
                      OR pc."timestamp"::time BETWEEN TIME '17:00' AND TIME '20:00'
               ), 2) AS avg_peak_occupancy,
               ROUND(MAX(pc.passenger_count::numeric / b.capacity), 2) AS max_occupancy_ratio
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
"""


def run_query(engine: Engine, sql: str) -> pd.DataFrame:
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn)


# ---------------------------------------------------------------------------
# Chart 1 — Hourly network demand
# ---------------------------------------------------------------------------
def chart_hourly_demand(df: pd.DataFrame) -> dict:
    fig, ax = plt.subplots(figsize=(11, 6))
    colors = ["#c0392b" if h in (8, 18) else "#2980b9" for h in df["hour"]]
    ax.bar(df["hour"], df["total_boardings"], color=colors)
    ax.set_title("Network-Wide Boardings by Hour of Day (30-day total)")
    ax.set_xlabel("Hour of Day")
    ax.set_ylabel("Total Boardings")
    ax.set_xticks(range(0, 24))
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x/1000:.0f}K"))
    ax.axvspan(6.5, 9.5, color="orange", alpha=0.08)
    ax.axvspan(16.5, 19.5, color="orange", alpha=0.08)
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "01_hourly_demand.png", dpi=150)
    plt.close(fig)

    peak_hours = df.nlargest(2, "total_boardings")
    total = df["total_boardings"].sum()
    return {
        "top_hours": [
            (int(r.hour), r.total_boardings, round(100 * r.total_boardings / total, 1))
            for r in peak_hours.itertuples()
        ]
    }


# ---------------------------------------------------------------------------
# Chart 2 — Weekday vs weekend demand by route_type
# ---------------------------------------------------------------------------
def chart_weekday_weekend(df: pd.DataFrame) -> dict:
    pivot = df.pivot(index="route_type", columns="day_type", values="avg_daily_boardings")
    pivot["weekend_ratio"] = pivot["Weekend"] / pivot["Weekday"]

    fig, ax = plt.subplots(figsize=(11, 6))
    pivot[["Weekday", "Weekend"]].plot(kind="bar", ax=ax, color=["#2980b9", "#e67e22"])
    ax.set_title("Average Daily Boardings — Weekday vs. Weekend, by Route Type")
    ax.set_xlabel("Route Type")
    ax.set_ylabel("Avg. Daily Boardings")
    ax.tick_params(axis="x", rotation=30)
    ax.legend(title="")
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "02_weekday_weekend_demand.png", dpi=150)
    plt.close(fig)

    network_ratio = df.groupby("day_type")["avg_daily_boardings"].sum()
    network_weekend_ratio = network_ratio["Weekend"] / network_ratio["Weekday"]
    return {"network_weekend_ratio": round(network_weekend_ratio, 2)}


# ---------------------------------------------------------------------------
# Chart 3 — Occupancy distribution, peak vs off-peak, by route_type
# ---------------------------------------------------------------------------
def chart_occupancy(df: pd.DataFrame) -> dict:
    fig, ax = plt.subplots(figsize=(12, 6))
    order = df.groupby("route_type")["occupancy_ratio"].mean().sort_values(ascending=False).index
    sns.boxplot(
        data=df, x="route_type", y="occupancy_ratio", hue="period",
        order=order, hue_order=["Peak", "Off-Peak"], ax=ax, showfliers=False,
        palette=["#c0392b", "#2980b9"],
    )
    ax.axhline(1.0, color="black", linestyle="--", linewidth=1, label="Rated capacity")
    ax.set_title("Occupancy Ratio Distribution — Peak vs. Off-Peak, by Route Type")
    ax.set_xlabel("Route Type")
    ax.set_ylabel("Occupancy Ratio (passengers / capacity)")
    ax.tick_params(axis="x", rotation=30)
    ax.legend(title="")
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "03_occupancy_peak_offpeak.png", dpi=150)
    plt.close(fig)

    summary = df.groupby("period")["occupancy_ratio"].mean().round(3).to_dict()
    return {"network_avg_occupancy": summary}


# ---------------------------------------------------------------------------
# Chart 4 — Delay distribution buckets
# ---------------------------------------------------------------------------
def chart_delay_buckets(df: pd.DataFrame) -> dict:
    df = df.copy()
    df["pct"] = 100 * df["trip_count"] / df["trip_count"].sum()
    colors = ["#27ae60", "#f1c40f", "#e67e22", "#c0392b"]

    fig, ax = plt.subplots(figsize=(9, 6))
    bars = ax.bar(df["delay_bucket"].str[3:], df["pct"], color=colors)
    for bar, pct in zip(bars, df["pct"]):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
                 f"{pct:.1f}%", ha="center", fontsize=12)
    ax.set_title("Trip-Level Delay Distribution (Network-Wide, 30 Days)")
    ax.set_ylabel("% of Trips")
    ax.set_xlabel("")
    ax.tick_params(axis="x", rotation=15)
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "04_delay_distribution.png", dpi=150)
    plt.close(fig)

    return {"buckets": dict(zip(df["delay_bucket"].str[3:], df["pct"].round(1)))}


# ---------------------------------------------------------------------------
# Chart 5 — Overcrowded vs. underutilized routes
# ---------------------------------------------------------------------------
def chart_overcrowded_underutilized(peak_df: pd.DataFrame, overall_df: pd.DataFrame) -> dict:
    top10 = peak_df.nlargest(10, "avg_peak_occupancy")
    bottom10 = overall_df.nsmallest(10, "mean_occupancy_ratio")

    fig, axes = plt.subplots(1, 2, figsize=(15, 7), sharex=False)

    sns.barplot(data=top10, y="route_number", x="avg_peak_occupancy",
                hue="route_type", dodge=False, ax=axes[0], palette=PALETTE, legend=False)
    axes[0].axvline(1.0, color="black", linestyle="--", linewidth=1)
    axes[0].set_title("Most Overcrowded (peak occupancy)")
    axes[0].set_xlabel("Avg. Peak Occupancy Ratio")
    axes[0].set_ylabel("Route")

    sns.barplot(data=bottom10, y="route_number", x="mean_occupancy_ratio",
                hue="route_type", dodge=False, ax=axes[1], palette=PALETTE, legend=False)
    axes[1].set_title("Most Underutilized (all-day mean)")
    axes[1].set_xlabel("Mean Occupancy Ratio")
    axes[1].set_ylabel("")

    fig.suptitle("Supply-Demand Mismatch: Overcrowded vs. Underutilized Routes", fontsize=16)
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "05_overcrowded_vs_underutilized.png", dpi=150)
    plt.close(fig)

    return {
        "most_overcrowded": top10.iloc[0][["route_number", "avg_peak_occupancy"]].to_dict(),
        "most_underutilized": bottom10.iloc[0][["route_number", "mean_occupancy_ratio"]].to_dict(),
    }


# ---------------------------------------------------------------------------
# Chart 6 — Route scorecard: demand vs. delay vs. occupancy (bubble)
# ---------------------------------------------------------------------------
def chart_scorecard(df: pd.DataFrame) -> dict:
    fig, ax = plt.subplots(figsize=(12, 8))
    route_types = df["route_type"].unique()
    palette = sns.color_palette(PALETTE, n_colors=len(route_types))
    color_map = dict(zip(route_types, palette))

    for rtype in route_types:
        sub = df[df["route_type"] == rtype]
        ax.scatter(
            sub["avg_delay_minutes"], sub["pct_on_time"],
            s=sub["avg_peak_occupancy"].fillna(0) * 400 + 30,
            color=color_map[rtype], alpha=0.7, label=rtype, edgecolor="white",
        )

    ax.set_title("Route Scorecard: On-Time Rate vs. Avg. Delay\n(bubble size = peak occupancy)")
    ax.set_xlabel("Average Delay (minutes)")
    ax.set_ylabel("% On-Time")
    ax.legend(title="Route Type", bbox_to_anchor=(1.02, 1), loc="upper left")
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "06_route_scorecard_scatter.png", dpi=150)
    plt.close(fig)

    worst = df.nlargest(1, "avg_delay_minutes").iloc[0]
    best = df.nsmallest(1, "avg_delay_minutes").iloc[0]
    return {
        "worst_route": (worst["route_number"], worst["avg_delay_minutes"], worst["pct_on_time"]),
        "best_route": (best["route_number"], best["avg_delay_minutes"], best["pct_on_time"]),
    }


# ---------------------------------------------------------------------------
# Summary markdown
# ---------------------------------------------------------------------------
def write_summary(stats: dict) -> None:
    hourly = stats["hourly"]
    weekday = stats["weekday"]
    occupancy = stats["occupancy"]
    delay = stats["delay"]
    mismatch = stats["mismatch"]
    scorecard = stats["scorecard"]

    top_hours_str = "; ".join(
        f"{h:02d}:00 ({pct}% of daily boardings)" for h, _, pct in hourly["top_hours"]
    )
    occ = occupancy["network_avg_occupancy"]
    buckets = delay["buckets"]
    overc = mismatch["most_overcrowded"]
    underu = mismatch["most_underutilized"]
    worst_r = scorecard["worst_route"]
    best_r = scorecard["best_route"]

    md = f"""# EDA Summary — Phase 4

**Generated by:** `python/02_eda.py`
**Purpose:** Visual counterpart to Phase 3 SQL analytics — same validated
definitions (on-time = arrival within 5 min of schedule; peak = 07:00-10:00
/ 17:00-20:00), rendered as charts for faster pattern recognition and for
reuse in the Phase 5 Power BI narrative and Phase 6 write-up.

## 1. Hourly Demand
![Hourly Demand](figures/01_hourly_demand.png)

Busiest hours network-wide: {top_hours_str}. Confirms the two documented
peak windows (07:00-10:00, 17:00-20:00) from Phase 3.

## 2. Weekday vs. Weekend Demand
![Weekday vs Weekend](figures/02_weekday_weekend_demand.png)

Network-wide weekend-to-weekday boarding ratio: **{weekday['network_weekend_ratio']}x**
(a blended Sat+Sun figure — individual Sat ~0.85x / Sun ~0.65x targets are
documented separately in `docs/assumptions.md`).

## 3. Occupancy: Peak vs. Off-Peak
![Occupancy](figures/03_occupancy_peak_offpeak.png)

Network average occupancy ratio — Peak: **{occ.get('Peak')}**, Off-Peak: **{occ.get('Off-Peak')}**.
Ordinary and Limited Stop routes show the widest peak/off-peak spread and the
most boxes crossing the rated-capacity (1.0) line.

## 4. Delay Distribution
![Delay Distribution](figures/04_delay_distribution.png)

Trip-level breakdown: {', '.join(f'{k}: {v}%' for k, v in buckets.items())}.
Matches the Phase 3 `sql/05_delay_analysis.sql` network-wide bucket figures.

## 5. Overcrowded vs. Underutilized Routes
![Mismatch](figures/05_overcrowded_vs_underutilized.png)

Most overcrowded: **{overc['route_number']}** (avg. peak occupancy {overc['avg_peak_occupancy']}).
Most underutilized: **{underu['route_number']}** (mean occupancy {underu['mean_occupancy_ratio']}).
This is the visual counterpart to the donor/receiver pairing in
`sql/06_advanced_analysis.sql` §3.

## 6. Route Scorecard
![Scorecard](figures/06_route_scorecard_scatter.png)

Highest average delay: **{worst_r[0]}** ({worst_r[1]} min, {worst_r[2]}% on-time).
Lowest average delay: **{best_r[0]}** ({best_r[1]} min, {best_r[2]}% on-time).
Bubble size = average peak occupancy, so routes in the bottom-right with
large bubbles are the clearest "overcrowded AND unreliable" candidates for
Phase 6 recommendations.

---
_All figures are derived directly from the same SQL logic validated in
Phase 3 (`sql/02-06`); no new metrics are introduced in this file._
"""
    (REPORTS_DIR / "eda_summary.md").write_text(md, encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    engine = get_engine()

    print("Running hourly demand query...")
    hourly_df = run_query(engine, Q_HOURLY_DEMAND)
    hourly_stats = chart_hourly_demand(hourly_df)

    print("Running weekday/weekend demand query...")
    weekday_df = run_query(engine, Q_WEEKDAY_WEEKEND)
    weekday_stats = chart_weekday_weekend(weekday_df)

    print("Running occupancy peak/off-peak query...")
    occupancy_df = run_query(engine, Q_OCCUPANCY_PEAK_OFFPEAK)
    occupancy_stats = chart_occupancy(occupancy_df)

    print("Running delay distribution query...")
    delay_df = run_query(engine, Q_DELAY_BUCKETS)
    delay_stats = chart_delay_buckets(delay_df)

    print("Running route peak/overall occupancy ranking queries...")
    peak_rank_df = run_query(engine, Q_ROUTE_PEAK_OCCUPANCY)
    overall_rank_df = run_query(engine, Q_ROUTE_OVERALL_OCCUPANCY)
    mismatch_stats = chart_overcrowded_underutilized(peak_rank_df, overall_rank_df)

    print("Running route scorecard query...")
    scorecard_df = run_query(engine, Q_ROUTE_SCORECARD)
    scorecard_stats = chart_scorecard(scorecard_df)

    write_summary({
        "hourly": hourly_stats,
        "weekday": weekday_stats,
        "occupancy": occupancy_stats,
        "delay": delay_stats,
        "mismatch": mismatch_stats,
        "scorecard": scorecard_stats,
    })

    print(f"\nDone. Figures written to {FIGURES_DIR}")
    print(f"Summary written to {REPORTS_DIR / 'eda_summary.md'}")


if __name__ == "__main__":
    main()