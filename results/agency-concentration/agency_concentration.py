# /// script
# requires-python = ">=3.10"
# dependencies = ["plotly", "kaleido"]
# ///
"""Graph: how concentrated are the outside searches of Kenner's cameras.

Reads:  cache/flock.db  (build it with the setup-scripts/ pipeline first)
Writes: next to this script, in results/agency-concentration/:
        agency_concentration.html  (interactive, self-contained)
        agency_concentration.svg
        agency_concentration.png

The database is the single source of data: the one SQL query below is
the whole calculation, and the script prints the top-20 table and the
band totals it draws, so the chart can be checked by re-running the
query against cache/flock.db.

Run from anywhere:  uv run results/agency-concentration/agency_concentration.py
(uv installs plotly and kaleido from the header above; see README.)

Definitions -- see DATA_DICTIONARY.md:
- "Outside agencies" = network_audit rows where org_name is NOT
  'Kenner LA PD' (same definition as results/internal-vs-network/).
- Agencies are grouped by TRIM(org_name): a few names carry trailing
  spaces in the export; trimming merges nothing (verified: no two
  distinct names collide after TRIM), it only cleans the labels.
- Treemap: rectangle area = share of all outside searches. Ranks 1-100
  are drawn individually inside their band (top 10 / 11-50 / 51-100);
  the 5,000+ agencies of the long tail are one aggregate block, because
  thousands of unreadable slivers would only pretend to be detail.
- This is a share-of-total chart, not a time series, so it uses the
  full data range including the partial last month (Jan 1 2024 -
  Jan 16 2026), stated in the subtitle.

Idempotent: re-running overwrites the three output files.
"""

import sqlite3
import sys
from pathlib import Path

import plotly.graph_objects as go

OUTPUT_DIR = Path(__file__).resolve().parent      # results/agency-concentration
PROJECT_ROOT = OUTPUT_DIR.parent.parent
DB_FILE = PROJECT_ROOT / "cache" / "flock.db"
OUTPUT_BASENAME = "agency_concentration"

# Known figures the query result must reproduce exactly (verified when
# this graph was built); any drift fails the run instead of drawing a
# wrong chart.
EXPECTED_TOTAL = 10_261_956
EXPECTED_AGENCY_COUNT = 5_254
EXPECTED_TOP = {
    "Houston TX PD": 1_008_621,
    "Dallas TX PD": 880_911,
}

# The three named bands; everything past rank 100 is the long tail.
BANDS = ((1, 10, "Top 10 agencies"),
         (11, 50, "Ranks 11-50"),
         (51, 100, "Ranks 51-100"))
BAND_COLORS = {"Top 10 agencies": "#2e5f8a",
               "Ranks 11-50": "#4f7ca6",
               "Ranks 51-100": "#7b9cba",
               "long tail": "#adc2d4"}

AGENCY_COUNTS = """
SELECT TRIM(org_name) AS agency, COUNT(*) AS searches
FROM network_audit
WHERE org_name != 'Kenner LA PD'
GROUP BY agency
ORDER BY searches DESC
"""


def build_figure(ranked, total):
    """Two-level treemap: band rectangles holding the named top-100
    agencies, plus one aggregate block for the long tail."""
    ids, labels, parents, values, colors = [], [], [], [], []

    for lo, hi, band in BANDS:
        band_rows = ranked[lo - 1:hi]
        band_total = sum(c for _, c in band_rows)
        ids.append(band)
        # the band header renders on one line, so the share goes in the
        # label itself (computed from the data, not hardcoded)
        labels.append(f"{band} — {100 * band_total / total:.1f}%")
        parents.append("")
        values.append(band_total)
        colors.append(BAND_COLORS[band])
        for agency, count in band_rows:
            ids.append(agency)
            labels.append(agency)
            parents.append(band)
            values.append(count)
            colors.append(BAND_COLORS[band])

    tail = ranked[100:]
    # a leaf node: the texttemplate below appends its share automatically
    ids.append("long tail")
    labels.append(f"{len(tail):,} other agencies (ranks 101+)")
    parents.append("")
    values.append(sum(c for _, c in tail))
    colors.append(BAND_COLORS["long tail"])

    fig = go.Figure(go.Treemap(
        ids=ids, labels=labels, parents=parents, values=values,
        branchvalues="total",
        marker=dict(colors=colors, line=dict(width=1, color="white")),
        texttemplate="%{label}<br>%{percentRoot:.1%}",
        hovertemplate="%{label}<br>%{value:,} searches"
                      " (%{percentRoot:.1%} of all outside searches)"
                      "<extra></extra>",
        pathbar=dict(visible=False),
        tiling=dict(pad=2),
    ))

    fig.update_layout(
        title=dict(
            text="Searches of Kenner's Flock cameras: two Texas agencies"
                 " vs. everyone else"
                 "<br><sup>All 10,261,956 searches by 5,254 outside agencies"
                 " that included Kenner's cameras, Jan 1 2024 - Jan 16 2026."
                 " Rectangle area = share of searches.</sup>"
                 "<br><sup>Ranks 1-100 are drawn individually (hover for"
                 " exact numbers in the interactive version); the long tail"
                 " is one block.</sup>",
        ),
        width=1100, height=700,
        margin=dict(t=110, b=80),
    )
    fig.add_annotation(
        text="Source: public record request (Flock audit logs"
             " Jan 2024 - Jan 16 2026, Kenner's own searches excluded):"
             ' <a href="https://www.muckrock.com/foi/kenner-16256/'
             'public-records-request-flock-audits-201972/">'
             "https://www.muckrock.com/foi/kenner-16256/"
             "public-records-request-flock-audits-201972/</a>"
             "<br>More info on the methodology on"
             ' <a href="https://github.com/eye-on-surveillance/'
             'foia-flock-kenner">github.com/eye-on-surveillance</a>',
        xref="paper", yref="paper", x=0, y=-0.06,
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
    ranked = connection.execute(AGENCY_COUNTS).fetchall()
    connection.close()

    # Verification: the known grand total, agency count, and top-2 counts
    # must match exactly -- otherwise the chart silently drifted from the
    # database.
    total = sum(c for _, c in ranked)
    print("Verification: query result vs known figures")
    checks = [
        ("total searches", total, EXPECTED_TOTAL),
        ("agencies", len(ranked), EXPECTED_AGENCY_COUNT),
    ] + [(name, dict(ranked)[name], count)
         for name, count in EXPECTED_TOP.items()]
    all_ok = True
    for label, got, expected in checks:
        ok = got == expected
        all_ok &= ok
        print(f"  {label}: {got:,} expected {expected:,}"
              f" {'OK' if ok else 'MISMATCH'}")
    if not all_ok:
        print("\nERROR: figures do not match; not writing outputs.",
              file=sys.stderr)
        sys.exit(1)

    print("\nTop 20 agencies:")
    cumulative = 0
    for rank, (agency, count) in enumerate(ranked[:20], start=1):
        cumulative += count
        print(f"  {rank:>3} {count:>9,} {100 * count / total:5.2f}%"
              f"  cum {100 * cumulative / total:5.2f}%  {agency}")

    print("\nBands drawn in the treemap:")
    for lo, hi, band in BANDS:
        band_total = sum(c for _, c in ranked[lo - 1:hi])
        print(f"  {band}: {band_total:,} searches"
              f" ({100 * band_total / total:.1f}%)")
    tail_total = sum(c for _, c in ranked[100:])
    print(f"  {len(ranked) - 100:,} other agencies (ranks 101+):"
          f" {tail_total:,} searches ({100 * tail_total / total:.1f}%)")

    fig = build_figure(ranked, total)
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
