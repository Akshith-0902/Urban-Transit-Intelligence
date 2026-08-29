"""
03_geospatial_analysis.py

Purpose: Geospatial mapping of demand density and delay hotspots across the
         real Chennai MTC stop network, using stops.latitude/longitude.
         Produces (a) a static overview map for the portfolio write-up and
         (b) an interactive Folium map for hands-on exploration, both built
         on the exact "priority stops" definition already validated in
         sql/06_advanced_analysis.sql §4.1 (top quartile for BOTH demand
         AND estimated delay).
Phase:   4 (Python Analysis)
Status:  DONE

Design note — stop-level delay is DERIVED, not stored
-------------------------------------------------------
Per sql/05_delay_analysis.sql's header: the schema only stores
scheduled_departure/scheduled_arrival at the TRIP level, so stop-level
delay is estimated by distributing scheduled duration proportionally
along route_stops.distance_from_origin_km. This script inherits that same
caveat unchanged — every stop-level delay figure here is an approximation
for spotting hotspots, not a precise measurement. Trip-level delay
(sql/03_route_performance.sql, already charted in 02_eda.py) remains the
reliable figure.

Usage
-----
    python python/03_geospatial_analysis.py

Outputs
-------
    reports/figures/07_stop_demand_delay_map.png   (static overview)
    reports/maps/priority_stops_map.html           (interactive Folium map)
    reports/geospatial_summary.md
"""

import os
import sys
from pathlib import Path

import folium
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from dotenv import load_dotenv
from folium.plugins import MarkerCluster
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, URL

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIGURES_DIR = PROJECT_ROOT / "reports" / "figures"
MAPS_DIR = PROJECT_ROOT / "reports" / "maps"
REPORTS_DIR = PROJECT_ROOT / "reports"
FIGURES_DIR.mkdir(parents=True, exist_ok=True)
MAPS_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Connection (same pattern as python/01_data_cleaning.py, python/02_eda.py)
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

# Per-stop demand + interpolated delay, joined to real lat/lon.
# The demand and stop_delay CTEs are reproduced verbatim from
# sql/06_advanced_analysis.sql §4.1 (which itself reuses the interpolation
# in sql/05_delay_analysis.sql §2) — this query just adds stops.latitude/
# longitude so the same figures can be mapped instead of tabulated, and
# does NOT apply the top-quartile filter (that's done in pandas below so
# the map can show all stops, with priority stops highlighted on top).
Q_STOP_DEMAND_DELAY = """
    WITH demand AS (
        SELECT stop_id, SUM(boardings + alightings) AS total_activity
        FROM passenger_counts
        GROUP BY stop_id
    ),
    stop_delay AS (
        SELECT pc.stop_id,
               AVG(EXTRACT(EPOCH FROM (
                   pc."timestamp" -
                   (t.scheduled_departure +
                    ((rs.distance_from_origin_km / r.total_distance_km) * r.scheduled_duration_min)
                        * INTERVAL '1 minute')
               )) / 60) AS avg_estimated_delay_min
        FROM passenger_counts pc
        JOIN trips t        ON t.trip_id = pc.trip_id
        JOIN routes r       ON r.route_id = t.route_id
        JOIN route_stops rs ON rs.route_id = t.route_id AND rs.stop_id = pc.stop_id
        GROUP BY pc.stop_id
    )
    SELECT s.stop_id, s.stop_name, s.latitude, s.longitude, s.zone,
           d.total_activity,
           ROUND(sd.avg_estimated_delay_min, 1) AS avg_estimated_delay_min
    FROM demand d
    JOIN stop_delay sd ON sd.stop_id = d.stop_id
    JOIN stops s        ON s.stop_id = d.stop_id
    ORDER BY d.total_activity DESC;
"""


def run_query(engine: Engine, sql: str) -> pd.DataFrame:
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn)


# ---------------------------------------------------------------------------
# Priority-stop flag — reproduces sql/06_advanced_analysis.sql §4.1's
# top-quartile-on-both-dimensions filter exactly, in pandas.
# ---------------------------------------------------------------------------
def flag_priority_stops(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    q3_activity = df["total_activity"].quantile(0.75)
    q3_delay = df["avg_estimated_delay_min"].quantile(0.75)
    df["is_priority"] = (df["total_activity"] >= q3_activity) & (
        df["avg_estimated_delay_min"] >= q3_delay
    )
    return df


# ---------------------------------------------------------------------------
# Static overview map (matplotlib scatter on lat/lon — no basemap tiles,
# but clear and portfolio-friendly; the Folium map below has real tiles)
# ---------------------------------------------------------------------------
def static_map(df: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(10, 11))

    non_priority = df[~df["is_priority"]]
    priority = df[df["is_priority"]]

    sc = ax.scatter(
        non_priority["longitude"], non_priority["latitude"],
        s=20 + (non_priority["total_activity"] / non_priority["total_activity"].max()) * 300,
        c=non_priority["avg_estimated_delay_min"], cmap="YlOrRd",
        alpha=0.75, edgecolor="grey", linewidth=0.3, vmin=df["avg_estimated_delay_min"].min(),
        vmax=df["avg_estimated_delay_min"].max(),
    )
    ax.scatter(
        priority["longitude"], priority["latitude"],
        s=20 + (priority["total_activity"] / df["total_activity"].max()) * 300,
        c=priority["avg_estimated_delay_min"], cmap="YlOrRd",
        edgecolor="blue", linewidth=2.2, vmin=df["avg_estimated_delay_min"].min(),
        vmax=df["avg_estimated_delay_min"].max(), zorder=5,
    )

    for _, row in priority.iterrows():
        ax.annotate(
            row["stop_name"], (row["longitude"], row["latitude"]),
            fontsize=8, xytext=(4, 4), textcoords="offset points",
        )

    cbar = fig.colorbar(sc, ax=ax, shrink=0.7, pad=0.02)
    cbar.set_label("Avg. Estimated Delay (min, interpolated)")

    ax.set_title(
        "Chennai MTC Stop Network — Demand (bubble size) vs.\n"
        "Estimated Delay (color) — blue ring = priority stop",
        fontsize=13,
    )
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_aspect("equal", adjustable="datalim")
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "07_stop_demand_delay_map.png", dpi=150)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Interactive Folium map
# ---------------------------------------------------------------------------
def folium_map(df: pd.DataFrame) -> None:
    center_lat = df["latitude"].mean()
    center_lon = df["longitude"].mean()
    m = folium.Map(location=[center_lat, center_lon], zoom_start=12, tiles="OpenStreetMap")

    max_activity = df["total_activity"].max()

    def delay_color(delay: float) -> str:
        if delay < 5:
            return "#27ae60"   # green — matches on-time bucket threshold
        elif delay < 15:
            return "#f1c40f"   # yellow — matches minor bucket
        elif delay < 30:
            return "#e67e22"   # orange — matches moderate bucket
        return "#c0392b"       # red — matches severe bucket

    cluster = MarkerCluster(name="All Stops").add_to(m)

    for _, row in df.iterrows():
        radius = 4 + 12 * (row["total_activity"] / max_activity)
        color = delay_color(row["avg_estimated_delay_min"])
        popup_html = (
            f"<b>{row['stop_name']}</b><br>"
            f"Total activity (boardings+alightings): {int(row['total_activity']):,}<br>"
            f"Est. avg delay: {row['avg_estimated_delay_min']:.1f} min<br>"
            f"{'<b style=\"color:blue\">PRIORITY STOP</b>' if row['is_priority'] else ''}"
        )
        folium.CircleMarker(
            location=[row["latitude"], row["longitude"]],
            radius=radius,
            color="blue" if row["is_priority"] else color,
            weight=3 if row["is_priority"] else 1,
            fill=True,
            fill_color=color,
            fill_opacity=0.75,
            popup=folium.Popup(popup_html, max_width=250),
        ).add_to(cluster)

    legend_html = """
    <div style="position: fixed; bottom: 30px; left: 30px; z-index: 9999;
                background: white; padding: 10px 14px; border: 1px solid #888;
                border-radius: 6px; font-size: 13px; line-height: 1.6;">
        <b>Est. Avg. Delay (interpolated)</b><br>
        <span style="color:#27ae60;">&#9679;</span> &lt; 5 min (on-time)<br>
        <span style="color:#f1c40f;">&#9679;</span> 5&ndash;15 min (minor)<br>
        <span style="color:#e67e22;">&#9679;</span> 15&ndash;30 min (moderate)<br>
        <span style="color:#c0392b;">&#9679;</span> &gt; 30 min (severe)<br>
        <span style="border:3px solid blue; border-radius:50%; padding:0 4px;">&#9675;</span>
        Priority stop (top quartile demand &amp; delay)<br>
        <i>Bubble size = total boardings + alightings</i>
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))
    folium.LayerControl().add_to(m)

    m.save(str(MAPS_DIR / "priority_stops_map.html"))


# ---------------------------------------------------------------------------
# Summary markdown
# ---------------------------------------------------------------------------
def write_summary(df: pd.DataFrame) -> None:
    priority = df[df["is_priority"]].sort_values("total_activity", ascending=False)
    top_delay = df.nlargest(5, "avg_estimated_delay_min")

    priority_rows = "\n".join(
        f"| {r.stop_name} | {r.zone} | {int(r.total_activity):,} | {r.avg_estimated_delay_min:.1f} |"
        for r in priority.itertuples()
    )
    top_delay_rows = "\n".join(
        f"| {r.stop_name} | {r.avg_estimated_delay_min:.1f} | {int(r.total_activity):,} |"
        for r in top_delay.itertuples()
    )

    md = f"""# Geospatial Analysis Summary — Phase 4

**Generated by:** `python/03_geospatial_analysis.py`
**Purpose:** Map demand and estimated delay across the real Chennai MTC
stop network, surfacing the same "priority stops" already flagged in
`sql/06_advanced_analysis.sql` §4.1 (top quartile for BOTH demand AND
estimated delay) — this file adds the geography, not new metrics.

**Caveat (inherited from `sql/05_delay_analysis.sql`):** stop-level delay
is *interpolated* by distributing each trip's scheduled duration
proportionally along `route_stops.distance_from_origin_km`, since the
schema only stores trip-level scheduled times. Treat these figures as
directional hotspot indicators, not precise measurements — trip-level
delay (`sql/03_route_performance.sql`, charted in `02_eda.py`) remains the
reliable figure.

## Static Overview
![Stop Demand/Delay Map](figures/07_stop_demand_delay_map.png)

Bubble size = total boardings + alightings at the stop; color = estimated
average delay; a blue ring marks a **priority stop** (top quartile on both
dimensions — {len(priority)} of {len(df)} stops qualify).

## Interactive Map
An interactive version with per-stop popups (hover for exact figures, click
markers to expand clusters) is saved separately at
[`reports/maps/priority_stops_map.html`](maps/priority_stops_map.html) —
open it directly in a browser (not renderable inline in Markdown/GitHub
previews).

## Priority Stops ({len(priority)} stops)

| Stop | Zone | Total Activity | Est. Avg Delay (min) |
|---|---|---:|---:|
{priority_rows}

These are the strongest candidates for on-the-ground investigation
(e.g. inadequate dwell time, junction congestion, signal timing) — high
enough demand that delay there affects many riders, and high enough
estimated delay that it's a real bottleneck rather than noise.

## Top 5 Stops by Estimated Delay (regardless of demand)

| Stop | Est. Avg Delay (min) | Total Activity |
|---|---:|---:|
{top_delay_rows}

Consistent with the Phase 3 finding that delay accumulates toward route
termini (`PROGRESS.md` §4): the highest-delay stops here are predominantly
end-of-line locations far from route origins.

---
_All figures derive from the same demand and interpolated-delay logic
validated in Phase 3 (`sql/05-06`), now joined to real stop coordinates;
no new metrics are introduced in this file._
"""
    (REPORTS_DIR / "geospatial_summary.md").write_text(md, encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    engine = get_engine()

    print("Running stop demand/delay query...")
    df = run_query(engine, Q_STOP_DEMAND_DELAY)
    df = flag_priority_stops(df)

    print(f"{len(df)} stops loaded; {df['is_priority'].sum()} flagged as priority stops.")

    print("Building static overview map...")
    static_map(df)

    print("Building interactive Folium map...")
    folium_map(df)

    print("Writing summary...")
    write_summary(df)

    print(f"\nDone.")
    print(f"Static map:      {FIGURES_DIR / '07_stop_demand_delay_map.png'}")
    print(f"Interactive map: {MAPS_DIR / 'priority_stops_map.html'}")
    print(f"Summary:         {REPORTS_DIR / 'geospatial_summary.md'}")


if __name__ == "__main__":
    main()