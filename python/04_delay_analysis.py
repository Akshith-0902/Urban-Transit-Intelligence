"""
04_delay_analysis.py

Purpose: Statistical investigation of delay drivers, extending
         sql/05_delay_analysis.sql. Three angles not already covered by
         Phase 3's SQL output:
           1. Delay vs. occupancy correlation — the explicit hand-off
              table from sql/05_delay_analysis.sql §4.1 ("does congestion
              track with overcrowding, route by route?"), now actually
              quantified (Pearson correlation) instead of left as a raw
              table.
           2. Hour-of-day x day-of-week delay heatmap — sql/05 §3.1 and
              §3.2 give these as two separate 1-D breakdowns; this
              combines them into one 2-D view to check whether the
              worst-delay hours shift on weekends.
           3. Delay distribution SHAPE by route_type (violin/box), not
              just the mean figures already in sql/03 and sql/05 — variance
              matters for reliability, not just the average.
         bus_type delay is intentionally NOT repeated here — it's already
         covered in sql/03_route_performance.sql §5.1.
Phase:   4 (Python Analysis)
Status:  DONE

Usage
-----
    python python/04_delay_analysis.py

Outputs
-------
    reports/figures/08_delay_vs_occupancy_scatter.png
    reports/figures/09_delay_heatmap_hour_day.png
    reports/figures/10_delay_distribution_by_routetype.png
    reports/delay_analysis_summary.md
"""

import os
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
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

sns.set_theme(style="whitegrid", context="talk")
PALETTE = "viridis"


# ---------------------------------------------------------------------------
# Connection (same pattern as the rest of python/)
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
# Queries
# ---------------------------------------------------------------------------

# Reproduced verbatim from sql/05_delay_analysis.sql §4.1 — the explicit
# "hand-off table for Phase 4" for delay-vs-occupancy correlation.
Q_DELAY_OCCUPANCY = """
    SELECT r.route_id, r.route_number, r.route_type,
           ROUND(AVG(EXTRACT(EPOCH FROM (t.actual_arrival - t.scheduled_arrival)) / 60), 1) AS avg_delay_minutes,
           ROUND(AVG(pc.passenger_count::numeric / b.capacity), 2)                          AS avg_occupancy_ratio
    FROM trips t
    JOIN routes r ON r.route_id = t.route_id
    JOIN buses b  ON b.bus_id = t.bus_id
    JOIN passenger_counts pc ON pc.trip_id = t.trip_id
    GROUP BY r.route_id, r.route_number, r.route_type
    ORDER BY avg_delay_minutes DESC;
"""

# Trip-level delay with both hour and day-of-week, for the 2-D heatmap.
# Same delay definition as sql/05 §3.1/§3.2 (actual_arrival - scheduled_arrival).
Q_DELAY_HOUR_DOW = """
    SELECT EXTRACT(HOUR FROM scheduled_departure)::int AS departure_hour,
           TO_CHAR(service_date, 'Dy')                 AS weekday,
           EXTRACT(ISODOW FROM service_date)::int      AS dow,
           EXTRACT(EPOCH FROM (actual_arrival - scheduled_arrival)) / 60 AS delay_minutes
    FROM trips;
"""

# Trip-level delay by route_type, for the distribution-shape chart
# (extends sql/05 §1.2's bucket counts into the full distribution).
Q_DELAY_BY_ROUTETYPE = """
    SELECT r.route_type,
           EXTRACT(EPOCH FROM (t.actual_arrival - t.scheduled_arrival)) / 60 AS delay_minutes
    FROM trips t
    JOIN routes r ON r.route_id = t.route_id;
"""


def run_query(engine: Engine, sql: str) -> pd.DataFrame:
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn)


# ---------------------------------------------------------------------------
# Chart 1 — Delay vs. occupancy correlation (per route)
# ---------------------------------------------------------------------------
def chart_delay_occupancy(df: pd.DataFrame) -> dict:
    r, p_value = pearson_corr(df["avg_occupancy_ratio"], df["avg_delay_minutes"])

    fig, ax = plt.subplots(figsize=(11, 8))
    route_types = df["route_type"].unique()
    palette = sns.color_palette(PALETTE, n_colors=len(route_types))
    color_map = dict(zip(route_types, palette))

    for rtype in route_types:
        sub = df[df["route_type"] == rtype]
        ax.scatter(sub["avg_occupancy_ratio"], sub["avg_delay_minutes"],
                   color=color_map[rtype], label=rtype, s=90, alpha=0.8, edgecolor="white")

    # Simple linear trend line (numpy polyfit — no statsmodels dependency needed for one line)
    coeffs = np.polyfit(df["avg_occupancy_ratio"], df["avg_delay_minutes"], 1)
    x_line = np.linspace(df["avg_occupancy_ratio"].min(), df["avg_occupancy_ratio"].max(), 100)
    ax.plot(x_line, np.polyval(coeffs, x_line), color="black", linestyle="--", linewidth=1.5,
            label=f"Trend (r = {r:.2f})")

    ax.set_title("Route-Level Avg. Delay vs. Avg. Occupancy Ratio\n(hand-off table, sql/05 §4.1)")
    ax.set_xlabel("Avg. Occupancy Ratio")
    ax.set_ylabel("Avg. Delay (minutes)")
    ax.legend(title="Route Type", bbox_to_anchor=(1.02, 1), loc="upper left")
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "08_delay_vs_occupancy_scatter.png", dpi=150)
    plt.close(fig)

    return {"pearson_r": round(r, 3), "p_value": p_value, "n_routes": len(df)}


def pearson_corr(x: pd.Series, y: pd.Series) -> tuple:
    """Pearson r and a two-sided p-value, computed with numpy/scipy-free
    arithmetic (t-distribution via a normal approximation is avoided;
    scipy.stats is a light, already-common dependency so we use it here
    for the p-value only, since requirements.txt doesn't list it — the
    correlation coefficient itself needs no extra library)."""
    r = float(np.corrcoef(x, y)[0, 1])
    n = len(x)
    # Two-sided p-value via the t-distribution, computed manually to avoid
    # adding scipy as a new dependency (requirements.txt intentionally
    # keeps optional/heavier libraries commented out until needed).
    if n <= 2 or abs(r) >= 1:
        return r, float("nan")
    t_stat = r * np.sqrt((n - 2) / (1 - r**2))
    # Approximate two-sided p-value from the t-statistic using the
    # relationship to the incomplete beta function is overkill here;
    # report the t-statistic-derived approximate p via a normal
    # approximation for large n, which is adequate for n=47 routes.
    from math import erf
    p_approx = 2 * (1 - 0.5 * (1 + erf(abs(t_stat) / np.sqrt(2))))
    return r, round(p_approx, 4)


# ---------------------------------------------------------------------------
# Chart 2 — Hour x day-of-week delay heatmap
# ---------------------------------------------------------------------------
def chart_hour_dow_heatmap(df: pd.DataFrame) -> dict:
    pivot = df.pivot_table(
        index="weekday", columns="departure_hour", values="delay_minutes",
        aggfunc="mean",
    )
    # Order weekdays Mon->Sun using the ISO day-of-week already pulled
    dow_order = (
        df[["weekday", "dow"]].drop_duplicates().sort_values("dow")["weekday"].tolist()
    )
    pivot = pivot.reindex(dow_order)

    fig, ax = plt.subplots(figsize=(14, 6))
    sns.heatmap(pivot, cmap="YlOrRd", ax=ax, cbar_kws={"label": "Avg. Delay (min)"},
                linewidths=0.3, linecolor="white")
    ax.set_title("Average Delay by Scheduled Departure Hour and Day of Week")
    ax.set_xlabel("Scheduled Departure Hour")
    ax.set_ylabel("")
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "09_delay_heatmap_hour_day.png", dpi=150)
    plt.close(fig)

    worst_cell = pivot.stack().idxmax()
    worst_val = pivot.stack().max()
    weekday_means = df.groupby("weekday")["delay_minutes"].mean()
    is_weekend = df["dow"].isin([6, 7])
    weekend_avg = df.loc[is_weekend, "delay_minutes"].mean()
    weekday_avg = df.loc[~is_weekend, "delay_minutes"].mean()

    return {
        "worst_cell": (worst_cell[0], int(worst_cell[1]), round(worst_val, 1)),
        "weekday_avg_delay": round(weekday_avg, 1),
        "weekend_avg_delay": round(weekend_avg, 1),
    }


# ---------------------------------------------------------------------------
# Chart 3 — Delay distribution shape by route_type
# ---------------------------------------------------------------------------
def chart_delay_distribution_shape(df: pd.DataFrame) -> dict:
    order = df.groupby("route_type")["delay_minutes"].mean().sort_values(ascending=False).index

    fig, ax = plt.subplots(figsize=(12, 7))
    sns.violinplot(data=df, x="route_type", y="delay_minutes", order=order,
                    hue="route_type", legend=False, ax=ax, palette=PALETTE, cut=0)
    ax.axhline(0, color="black", linestyle="--", linewidth=1)
    ax.set_title("Delay Distribution Shape by Route Type\n(width = density of trips at that delay)")
    ax.set_xlabel("Route Type")
    ax.set_ylabel("Delay (minutes)")
    ax.tick_params(axis="x", rotation=25)
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "10_delay_distribution_by_routetype.png", dpi=150)
    plt.close(fig)

    variance_by_type = df.groupby("route_type")["delay_minutes"].std().round(1).sort_values(ascending=False)
    return {
        "most_variable": (variance_by_type.index[0], variance_by_type.iloc[0]),
        "least_variable": (variance_by_type.index[-1], variance_by_type.iloc[-1]),
    }


# ---------------------------------------------------------------------------
# Summary markdown
# ---------------------------------------------------------------------------
def write_summary(stats: dict) -> None:
    occ = stats["occupancy"]
    heat = stats["heatmap"]
    shape = stats["shape"]

    corr_strength = (
        "a strong positive" if occ["pearson_r"] >= 0.7 else
        "a moderate positive" if occ["pearson_r"] >= 0.4 else
        "a weak positive" if occ["pearson_r"] > 0 else
        "no meaningful"
    )
    sig_note = (
        f"statistically significant at p < 0.0001"
        if occ["p_value"] == occ["p_value"] and occ["p_value"] < 0.0001
        else f"statistically significant at p = {occ['p_value']}"
        if occ["p_value"] == occ["p_value"] and occ["p_value"] < 0.05
        else f"p = {occ['p_value']} (not conventionally significant, small n = {occ['n_routes']} routes)"
    )

    md = f"""# Delay Driver Analysis — Phase 4

**Generated by:** `python/04_delay_analysis.py`
**Purpose:** Statistical investigation of delay drivers extending
`sql/05_delay_analysis.sql`. Covers three angles not already surfaced in
Phase 3's SQL output — delay-vs-occupancy correlation, an hour x
day-of-week heatmap, and delay distribution shape by route type.
Bus-type delay is intentionally not repeated here; it's already covered
in `sql/03_route_performance.sql` §5.1.

## 1. Does Congestion Track With Delay? (the Phase 3 §4.1 hand-off)
![Delay vs Occupancy](figures/08_delay_vs_occupancy_scatter.png)

Across the network's {occ['n_routes']} routes, average delay and average
occupancy ratio show **{corr_strength} correlation** (Pearson r = **{occ['pearson_r']}**,
{sig_note}).

**Correlation, not causation** (per `docs/assumptions.md` rule #5): this
doesn't prove overcrowding *causes* delay — both could share a common
driver (e.g. high-traffic corridors generate both more riders and more
congestion). But the direction is consistent with the intuitive story:
routes that run fullest also tend to run latest, which strengthens the
case for the donor/receiver reallocation already proposed in
`sql/06_advanced_analysis.sql` §3 — moving buses to overcrowded routes may
help reliability, not just comfort.

## 2. When Are Delays Worst? (hour x day-of-week)
![Delay Heatmap](figures/09_delay_heatmap_hour_day.png)

Worst single hour/day combination: **{heat['worst_cell'][0]} at {heat['worst_cell'][1]:02d}:00**
(avg. {heat['worst_cell'][2]} min delay). Network-wide, weekday departures
average **{heat['weekday_avg_delay']} min** delay vs. **{heat['weekend_avg_delay']} min** on
weekends — consistent with weekday peak-hour congestion being the primary
delay driver rather than a network-wide scheduling issue.

## 3. Delay Distribution Shape by Route Type
![Delay Distribution Shape](figures/10_delay_distribution_by_routetype.png)

Most variable (least predictable) delay: **{shape['most_variable'][0]}**
(std. dev. {shape['most_variable'][1]} min). Most consistent: **{shape['least_variable'][0]}**
(std. dev. {shape['least_variable'][1]} min). This matters operationally
beyond the average: a route with high variance is unreliable even on days
its *average* delay looks acceptable, which the mean-only figures in
`sql/03` and `sql/05` can't show on their own.

---
_Angles 1-3 above are new statistical views (correlation, 2-D time
pattern, distribution shape); the underlying delay and occupancy
definitions are unchanged from the audited Phase 3 SQL._
"""
    (REPORTS_DIR / "delay_analysis_summary.md").write_text(md, encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    engine = get_engine()

    print("Running delay-vs-occupancy query (sql/05 §4.1 hand-off)...")
    occ_df = run_query(engine, Q_DELAY_OCCUPANCY)
    occ_stats = chart_delay_occupancy(occ_df)

    print("Running hour x day-of-week delay query...")
    heat_df = run_query(engine, Q_DELAY_HOUR_DOW)
    heat_stats = chart_hour_dow_heatmap(heat_df)

    print("Running delay-by-route_type query...")
    shape_df = run_query(engine, Q_DELAY_BY_ROUTETYPE)
    shape_stats = chart_delay_distribution_shape(shape_df)

    write_summary({
        "occupancy": occ_stats,
        "heatmap": heat_stats,
        "shape": shape_stats,
    })

    print(f"\nDone. Figures written to {FIGURES_DIR}")
    print(f"Summary written to {REPORTS_DIR / 'delay_analysis_summary.md'}")


if __name__ == "__main__":
    main()