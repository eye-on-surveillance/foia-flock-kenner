# /// script
# requires-python = ">=3.10"
# dependencies = ["plotly", "kaleido"]
# ///
"""Graph: Kenner PD's own searches vs. outside-agency searches, per month.

Reads:  cache/flock.db  (build it with the setup-scripts/ pipeline first)
Writes: next to this script, in results/internal-vs-network/:
        internal_vs_network.html  (interactive, self-contained)
        internal_vs_network.svg
        internal_vs_network.png

The database is the single source of data: the two SQL queries below are
the whole calculation, and the script prints the monthly numbers it
plots, so the chart can be checked by re-running the queries against
cache/flock.db.

Run from anywhere:  uv run results/internal-vs-network/internal_vs_network.py
(uv installs plotly and kaleido from the header above; see README.)

Definitions -- see DATA_DICTIONARY.md:
- "Kenner PD internal searches" = every row of org_audit (searches run by
  Kenner's own users; org_name is 'Kenner LA PD' on all 66,933 rows).
- "External network searches" = network_audit rows where org_name is NOT
  'Kenner LA PD'. Kenner also appears 65,879 times in its own network audit;
  those rows are excluded here so the two curves never count the same
  search twice.
- January 2026 is excluded: the FOIA response only covers it through
  Jan 16, and a half month would read as a fake drop.

Idempotent: re-running overwrites the three output files.
"""

import sqlite3
import sys
from pathlib import Path

import plotly.graph_objects as go

OUTPUT_DIR = Path(__file__).resolve().parent      # results/internal-vs-network
PROJECT_ROOT = OUTPUT_DIR.parent.parent
DB_FILE = PROJECT_ROOT / "cache" / "flock.db"
OUTPUT_BASENAME = "internal_vs_network"

# The chart covers the 24 complete months, Jan 2024 - Dec 2025.
LAST_FULL_MONTH = "2025-12"

# Grand totals the monthly buckets must add up to: the pipeline's known
# row counts (README stage 1) minus the excluded partial month
# (Jan 2026: 1,059 internal rows, 282,937 external rows).
EXPECTED_INTERNAL_TOTAL = 66_933 - 1_059    # = 65,874
EXPECTED_EXTERNAL_TOTAL = 10_261_956 - 282_937  # = 9,979,019

# search_time is ISO-8601 text ('2024-01-25T13:27:03Z'), so its first
# 7 characters are the month, 'YYYY-MM'. substr() keeps the grouping
# trivially checkable against the raw strings.
MONTHLY_INTERNAL = """
SELECT substr(search_time, 1, 7) AS month, COUNT(*) AS searches
FROM org_audit
WHERE month <= ?
GROUP BY month
ORDER BY month
"""

MONTHLY_EXTERNAL = """
SELECT substr(search_time, 1, 7) AS month, COUNT(*) AS searches
FROM network_audit
WHERE org_name != 'Kenner LA PD' AND month <= ?
GROUP BY month
ORDER BY month
"""


def monthly_counts(connection, query):
    """Run one of the monthly-count queries; returns {month: count}."""
    return dict(connection.execute(query, (LAST_FULL_MONTH,)).fetchall())


def check_total(label, counts, expected):
    """Print one audit line; returns True when the total matches."""
    total = sum(counts.values())
    status = "OK" if total == expected else "MISMATCH"
    print(f"  {label}: total={total} expected={expected} {status}")
    return total == expected


def build_figure(months, internal, external):
    """One chart: external volume as bars, Kenner's own as a line on top.
    """
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=months, y=[external[m] for m in months],
        name="Outside agencies (left axis)",
        marker_color="#d5866f",
        hovertemplate="%{x}: %{y:,} external searches<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=months, y=[internal[m] for m in months],
        name="Kenner PD itself (right axis)",
        mode="lines+markers", line=dict(color="#1a5276", width=3),
        yaxis="y2",
        hovertemplate="%{x}: %{y:,} Kenner PD searches<extra></extra>",
    ))

    fig.update_layout(
        title=dict(
            text="Flock camera searches: Kenner PD vs. the rest of the network"
                 "<br><sup>Two different y-axis scales: outside agencies"
                 " (bars, left, peaks ~550,000/month) search ~150x more than"
                 " Kenner itself (line, right, peaks ~4,300/month).</sup>",
        ),
        # Explicit range so the axis stops right after the Dec 2025 bar;
        # otherwise plotly pads the edge and labels it "Jan 2026".
        xaxis=dict(tickformat="%b %Y", dtick="M3", tick0="2024-01-01",
                   range=["2023-12-15", "2025-12-17"]),
        yaxis=dict(
            title=dict(text="Searches by outside agencies / month",
                       font=dict(color="#b3543a")),
            tickfont=dict(color="#b3543a"),
            rangemode="tozero", separatethousands=True,
        ),
        yaxis2=dict(
            title=dict(text="Searches by Kenner PD / month",
                       font=dict(color="#1a5276")),
            tickfont=dict(color="#1a5276"),
            overlaying="y", side="right",
            rangemode="tozero", separatethousands=True,
        ),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0),
        width=1000, height=600,
        margin=dict(b=90),
    )
    fig.add_annotation(
        text="Source: Kenner LA PD FOIA response via MuckRock (Flock audit"
             " logs). Full months only: Jan 2024 - Dec 2025."
             " Methodology: results/internal-vs-network/ in the"
             " eos-foia-flock-kenner repo.",
        xref="paper", yref="paper", x=0, y=-0.18,
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
    internal = monthly_counts(connection, MONTHLY_INTERNAL)
    external = monthly_counts(connection, MONTHLY_EXTERNAL)
    connection.close()

    # Verification: the monthly buckets must add up exactly to the known
    # grand totals -- otherwise the chart silently dropped rows.
    print("Verification: monthly buckets vs known totals")
    totals_ok = check_total("internal (org_audit)", internal,
                            EXPECTED_INTERNAL_TOTAL)
    totals_ok &= check_total("external (network_audit minus Kenner)",
                             external, EXPECTED_EXTERNAL_TOTAL)
    if not totals_ok:
        print("\nERROR: totals do not match; not writing outputs.",
              file=sys.stderr)
        sys.exit(1)

    # Both queries cover the same 24 months, but take the union anyway so
    # a month present in only one table could never be dropped silently.
    months = sorted(set(internal) | set(external))
    internal = {m: internal.get(m, 0) for m in months}
    external = {m: external.get(m, 0) for m in months}

    print(f"\n{'month':<8} {'kenner_internal':>15} {'external_network':>16}")
    for m in months:
        print(f"{m:<8} {internal[m]:>15,} {external[m]:>16,}")

    fig = build_figure(months, internal, external)
    html_path = OUTPUT_DIR / f"{OUTPUT_BASENAME}.html"
    svg_path = OUTPUT_DIR / f"{OUTPUT_BASENAME}.svg"
    png_path = OUTPUT_DIR / f"{OUTPUT_BASENAME}.png"
    fig.write_html(html_path)                # self-contained interactive page
    fig.write_image(svg_path)                # static, via kaleido
    fig.write_image(png_path, scale=2)       # static, 2x resolution

    print()
    for path in (html_path, svg_path, png_path):
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
