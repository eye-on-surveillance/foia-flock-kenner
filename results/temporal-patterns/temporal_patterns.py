# /// script
# requires-python = ">=3.10"
# dependencies = ["plotly", "kaleido"]
# ///
"""Heatmap: when do Flock searches happen? Hour-of-day × day-of-week.

Reads:  cache/flock.db  (build it with the setup-scripts/ pipeline first)
Writes: next to this script, in results/temporal-patterns/:
        temporal_patterns.html  (interactive, self-contained)
        temporal_patterns.svg
        temporal_patterns.png

Two side-by-side heatmaps reveal whether searches are human-driven
(concentrated in business hours, weekdays) or automated (spread across
all hours, including nights and weekends):

  Left:  Kenner PD's own searches (org_audit, 66,933 rows)
  Right: Outside agencies searching Kenner's cameras (network_audit
         minus Kenner's own rows, 10,261,956 rows)

Timestamps are converted from UTC to Central Time (UTC-6). This is
approximate — CDT (UTC-5) applies part of the year — but the 1-hour
shift doesn't change the patterns in a 2-year aggregate.

Run from anywhere:  uv run results/temporal-patterns/temporal_patterns.py
"""

import sqlite3
import sys
from pathlib import Path

OUTPUT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = OUTPUT_DIR.parent.parent
DB_FILE = PROJECT_ROOT / "cache" / "flock.db"
OUTPUT_BASENAME = "temporal_patterns"

DOW_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# SQLite's strftime modifier '-6 hours' shifts both hour and weekday
# correctly, so a 3am UTC search on Tuesday becomes 9pm Monday CT.
QUERY_TEMPLATE = """
    SELECT cast(strftime('%w', search_time, '-6 hours') as integer) AS dow,
           cast(strftime('%H', search_time, '-6 hours') as integer) AS hour,
           COUNT(*) AS searches
    FROM {table}
    {where}
    GROUP BY dow, hour
"""

DATASETS = [
    {
        "label": "Kenner PD internal",
        "subplot_label": "Kenner PD's own searches",
        "expected": 66_933,
        "query": QUERY_TEMPLATE.format(table="org_audit", where=""),
    },
    {
        "label": "Outside agencies",
        "subplot_label": "Outside agencies",
        "expected": 10_261_956,
        "query": QUERY_TEMPLATE.format(
            table="network_audit",
            where="WHERE org_name != 'Kenner LA PD'",
        ),
    },
]


def query_heatmap_data(connection, query):
    """Run a dow×hour query; returns a 7×24 grid (rows=days, cols=hours)."""
    grid = [[0] * 24 for _ in range(7)]
    total = 0
    for sqlite_dow, hour, count in connection.execute(query).fetchall():
        grid[(sqlite_dow - 1) % 7][hour] = count
        total += count
    return grid, total


def print_summary_stats(label, grid, total):
    """Print quotable statistics about search timing patterns."""
    biz_hours = sum(grid[d][h] for d in range(5) for h in range(8, 18))
    overnight = sum(grid[d][h] for d in range(7) for h in (*range(0, 6), *range(22, 24)))
    weekend = sum(grid[d][h] for d in (5, 6) for h in range(24))

    pct = lambda n: f"{n / total * 100:.1f}%"
    print(f"\n{label} — summary statistics:")
    print(f"  Business hours (Mon-Fri, 8am-6pm): {biz_hours:>10,}  ({pct(biz_hours)})")
    print(f"  Overnight      (10pm-6am):         {overnight:>10,}  ({pct(overnight)})")
    print(f"  Weekends       (Sat-Sun):           {weekend:>10,}  ({pct(weekend)})")

    flat = [(DOW_LABELS[d], h, grid[d][h]) for d in range(7) for h in range(24)]
    print("  Top 5 busiest hours:")
    for day, hour, count in sorted(flat, key=lambda x: -x[2])[:5]:
        print(f"    {day} {hour:>2d}:00 — {count:,} searches")


def build_figure(grids):
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=[
            f"{ds['subplot_label']} ({ds['expected']:,})" for ds in DATASETS
        ],
        horizontal_spacing=0.08,
    )

    common = dict(
        y=DOW_LABELS,
        x=[f"{h}:00" for h in range(24)],
        colorscale="YlOrRd",
        hovertemplate="%{y} %{x} CT<br>%{z:,} searches<extra></extra>",
    )

    for col, grid in enumerate(grids, 1):
        fig.add_trace(
            go.Heatmap(z=grid, showscale=(col == len(grids)), **common),
            row=1, col=col,
        )

    fig.update_xaxes(title_text="Hour (Central Time)", dtick=3)
    fig.update_yaxes(autorange="reversed")

    fig.update_layout(
        title=dict(
            text="When do Flock searches happen?"
                 "<br><sup>Hour-of-day × day-of-week heatmap (color scales are independent)."
                 " Concentrated blocks = human-driven."
                 " Uniform spread = automated.</sup>",
        ),
        width=1100, height=500,
        margin=dict(b=130),
    )

    fig.add_annotation(
        text="Source: public record request (Flock audit logs,"
             " Jan 2024 - Jan 2026):"
             '<br><a href="https://www.muckrock.com/foi/kenner-16256/'
             'public-records-request-flock-audits-201972/">'
             "https://www.muckrock.com/foi/kenner-16256/"
             "public-records-request-flock-audits-201972/</a>"
             "<br>Times shown in Central Time (UTC-6, approximate)."
             " More info on"
             ' <a href="https://github.com/eye-on-surveillance/'
             'foia-flock-kenner">github.com/eye-on-surveillance</a>',
        xref="paper", yref="paper", x=0, y=-0.25,
        showarrow=False, font=dict(size=10, color="#666"),
    )

    return fig


def main():
    if not DB_FILE.exists():
        print(f"ERROR: {DB_FILE} not found."
              "\nRun the setup-scripts/ pipeline (00, 01_*, 02) first.",
              file=sys.stderr)
        sys.exit(1)

    connection = sqlite3.connect(DB_FILE)
    grids, totals_ok = [], True

    print("Verification: grid totals vs known row counts")
    for ds in DATASETS:
        grid, total = query_heatmap_data(connection, ds["query"])
        grids.append(grid)
        status = "OK" if total == ds["expected"] else "MISMATCH"
        print(f"  {ds['label']}: total={total:,} expected={ds['expected']:,} {status}")
        totals_ok &= total == ds["expected"]
        ds["_grid"], ds["_total"] = grid, total

    connection.close()

    if not totals_ok:
        print("\nERROR: totals do not match; not writing outputs.", file=sys.stderr)
        sys.exit(1)

    for ds in DATASETS:
        print_summary_stats(ds["label"], ds["_grid"], ds["_total"])

    fig = build_figure(grids)
    for ext in ("html", "svg", "png"):
        path = OUTPUT_DIR / f"{OUTPUT_BASENAME}.{ext}"
        if ext == "html":
            fig.write_html(path)
        else:
            fig.write_image(path, scale=2 if ext == "png" else 1)
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
