# /// script
# requires-python = ">=3.10"
# dependencies = ["plotly", "kaleido"]
# ///
"""Graph: Kenner PD's 2025 Flock searches -- what they were for (top panel)
and which outside agencies used Kenner's camera network for immigration
purposes (bottom panel). Each bar carries example raw 'reason' strings in
a column on the right, so the real typed text behind every row is visible.

Reads:  cache/flock.db  (build it with the setup-scripts/ pipeline first)
Writes: next to this script, in results/search-reasons-2025/:
        search_reasons_2025.html  (interactive, self-contained)
        search_reasons_2025.svg
        search_reasons_2025.png

The database is the single source of data: the queries below are the
whole calculation, and the example strings are computed from the db at
run time, never hardcoded. The script refuses to write outputs unless
three known totals check out: Kenner's 38,037 searches of 2025 (top
panel buckets), the 6,291 immigration-connected network searches
(bottom panel rows), and the 6,207,233 outside-agency network searches
of 2025 (the bottom panel's denominator).

The `reason` column is free text typed by the officer, so both panels
rest on editorial matching rules; the rules are the LIKE/GLOB patterns
visible in the queries and are documented with examples in this folder's
README.md. Two transparency printouts keep the judgment calls auditable:
- every raw reason string that lands in the top panel's immigration
  bucket (currently 11 rows, all 'HSI'/'Assist HSI');
- every network-audit row removed as a false positive of the broad
  immigration term-match (currently 40 rows -- 'ice cream thefts',
  'ICE STORM', ...), plus the full per-agency list behind the bottom
  panel (the chart shows only the top 20).

Run from anywhere:  uv run results/search-reasons-2025/search_reasons_2025.py
(uv installs plotly and kaleido from the header above; see README.)

Idempotent: re-running overwrites the three output files.
"""

import sqlite3
import sys
from pathlib import Path

import plotly.graph_objects as go
from plotly.subplots import make_subplots

OUTPUT_DIR = Path(__file__).resolve().parent      # results/search-reasons-2025
PROJECT_ROOT = OUTPUT_DIR.parent.parent
DB_FILE = PROJECT_ROOT / "cache" / "flock.db"
OUTPUT_BASENAME = "search_reasons_2025"

# Known 2025 totals (see README for the underlying one-line queries):
#   org_audit rows in 2025                          -> 38,037
#   network_audit rows with an immigration
#   connection (term-matched reason minus reviewed
#   false positives, or HSI/Border Patrol searching
#   directly), 2025                                 ->  6,291
#   network_audit rows in 2025, Kenner excluded     -> 6,207,233
EXPECTED_TOTAL = 38_037
EXPECTED_IMMIGRATION_TOTAL = 6_291
EXPECTED_NETWORK_TOTAL = 6_207_233

TOP_AGENCIES = 20                    # bars shown in the bottom panel

BAR_COLOR = "#1a5276"        # same blue as the other Kenner-PD series
HIGHLIGHT_COLOR = "#b3543a"  # rust, reserved for immigration
HIGHLIGHT_CATEGORY = "Immigration (HSI / ICE)"

# The immigration term-match, shared by both panels. Applied to
# l = LOWER(TRIM(reason)) and p = ' '||l||' '; the padded copy makes
# ' ice ' / ' ero ' match whole words only ('police' and 'hero' must
# not match).
IMMIGRATION_TERMS = """(l LIKE '%hsi%' OR p LIKE '% ice %' OR p LIKE '% ero %'
       OR l LIKE '%immigr%' OR l LIKE '%deport%' OR l LIKE '%alien%')"""

# Phrases the broad term-match catches that are NOT the agency, found by
# hand-reviewing every distinct matched phrase in the network audit (the
# README shows each excluded row in full; the script prints them too, so
# this list can never silently drop anything new).
FALSE_POSITIVES = """(l LIKE '%lemon ice%' OR l LIKE '%ice storm%'
       OR l LIKE '%ice cream%' OR l LIKE '%vegan ice%'
       OR l LIKE '%mtn ice%' OR l LIKE '%threats to ice agents%')"""

# The two immigration agencies that appear by name among the outside
# agencies searching networks that include Kenner's cameras; their rows
# count regardless of the typed reason.
IMMIGRATION_ORGS = """('[Federal] Homeland Security Investigations [Inactive]',
        '[Federal] US Border Patrol [Inactive]')"""

# ---------------------------------------------------------------- panel 1
# One bucket per 2025 Kenner search; CASE arms are checked top to
# bottom, so the more specific matches (immigration, stolen, suspect...)
# win before the catch-alls.
CATEGORY_CASE = f"""CASE
        WHEN {IMMIGRATION_TERMS}
            THEN '{HIGHLIGHT_CATEGORY}'
        WHEN l LIKE '%stolen%' OR l LIKE '%stoen%'
            THEN 'Stolen vehicle / plate'
        WHEN l LIKE '%suspect%' OR l LIKE '%wanted%' OR l LIKE '%warrant%'
          OR l LIKE '%fugitive%' OR l LIKE '%suspicious%'
            THEN 'Suspect / wanted / warrant'
        WHEN l LIKE '%missing%' OR l LIKE '%welfare%' OR l LIKE '%locate%'
          OR l = 'suicidal'
            THEN 'Missing person / welfare'
        WHEN l LIKE '%narcotic%' OR l LIKE '%drug%' OR l LIKE 'burg%'
          OR l LIKE '%burglar%' OR l LIKE '%shooting%' OR l LIKE '%shoting%'
          OR l LIKE '%extortion%' OR l LIKE '%extotion%' OR l LIKE '%assault%'
          OR l LIKE '%hit and run%' OR l LIKE '%hit run%' OR l LIKE '%hit & run%'
          OR l LIKE '%theft%' OR l LIKE '%homicide%' OR l LIKE '%robbery%'
          OR l LIKE '%murder%' OR l LIKE '%carjack%' OR l LIKE '%rape%'
          OR l LIKE '%kidnap%' OR l LIKE '%battery%' OR l LIKE '%arson%'
          OR l LIKE '%fraud%' OR l LIKE '%reckless%' OR l LIKE 'ran from%'
          OR l LIKE '%escape%' OR l = 'pursuit' OR l = 'crash' OR l = 'traffic'
          OR l = 'disturbance' OR l = 'mischief' OR l = 'sex offender'
            THEN 'Named crime or incident'
        WHEN l GLOB '[0-9]*' OR l LIKE 'cfs%' OR l LIKE 'patrol cfs%'
          OR l LIKE '%signal%'
            THEN 'Numeric / signal code'
        WHEN l GLOB '[a-z]-[0-9]*' OR l GLOB '[a-z][0-9][0-9][0-9]*'
            THEN 'Case number only'
        WHEN l LIKE 'inv%' OR l LIKE '%investigat%' OR l LIKE 'inestigation%'
          OR l LIKE 'ivestigation%'
          OR l IN ('in', 'i n', 'inquiry', 'vehicle inquiry', 'vehicle',
                   'c', 'l', 'i', '.', 'sus', 'nid', 'undefined', 'test',
                   'dispo', 'disp', 'diso')
            THEN 'Generic / vague'
        ELSE 'Other'
    END"""

ORG_CTE = """
WITH r AS (
    SELECT TRIM(reason) AS reason,
           LOWER(TRIM(reason)) AS l,
           ' ' || LOWER(TRIM(reason)) || ' ' AS p
    FROM org_audit
    WHERE search_time >= '2025-01-01' AND search_time < '2026-01-01'
)
"""

CATEGORY_QUERY = f"""
{ORG_CTE},
cat AS (SELECT {CATEGORY_CASE} AS category FROM r)
SELECT category, COUNT(*) AS searches
FROM cat
GROUP BY category
ORDER BY searches DESC
"""

# Same bucketing, but keeping the raw reason: feeds the example column
# (top raw reasons per bucket) shown right of the top panel.
CATEGORY_EXAMPLES_QUERY = f"""
{ORG_CTE},
cat AS (SELECT reason, {CATEGORY_CASE} AS category FROM r)
SELECT category, reason, COUNT(*) AS searches
FROM cat
GROUP BY category, reason
ORDER BY category, searches DESC
"""

# Transparency check for the sensitive bucket: list every raw reason
# string the immigration arm matched on Kenner's own searches. The term
# list is broad on purpose; instead of pre-excluding false positives
# with a hidden denylist, this prints what actually matched so a false
# positive could never go unnoticed.
IMMIGRATION_DETAIL_QUERY = f"""
{ORG_CTE}
SELECT reason, COUNT(*) AS searches
FROM r
WHERE {IMMIGRATION_TERMS}
GROUP BY reason
ORDER BY searches DESC
"""

# ---------------------------------------------------------------- panel 2
# Outside agencies' immigration use of networks that include Kenner's
# cameras: a row counts when its reason matches the immigration terms
# (and is not a reviewed false positive), or when the searching agency
# is itself HSI or Border Patrol.
NETWORK_CTE = """
WITH n AS (
    SELECT org_name, TRIM(reason) AS reason,
           LOWER(TRIM(COALESCE(reason, ''))) AS l,
           ' ' || LOWER(TRIM(COALESCE(reason, ''))) || ' ' AS p
    FROM network_audit
    WHERE search_time >= '2025-01-01' AND search_time < '2026-01-01'
)
"""

AGENCY_QUERY = f"""
{NETWORK_CTE}
SELECT org_name, COUNT(*) AS searches
FROM n
WHERE ({IMMIGRATION_TERMS} AND NOT {FALSE_POSITIVES})
   OR org_name IN {IMMIGRATION_ORGS}
GROUP BY org_name
ORDER BY searches DESC, org_name
"""

# Top typed reasons per agency among the term-matched rows: feeds the
# example column right of the bottom panel.
AGENCY_EXAMPLES_QUERY = f"""
{NETWORK_CTE}
SELECT org_name, reason, COUNT(*) AS searches
FROM n
WHERE {IMMIGRATION_TERMS} AND NOT {FALSE_POSITIVES}
GROUP BY org_name, reason
ORDER BY org_name, searches DESC
"""

# HSI and Border Patrol are counted by agency, not by reason, so their
# examples come from their own most-typed reasons (case numbers, 'Human
# Trafficking', 'USBP', ...) -- honest about what they actually typed.
FED_EXAMPLES_QUERY = f"""
{NETWORK_CTE}
SELECT org_name, COALESCE(NULLIF(reason, ''), '(blank)') AS reason,
       COUNT(*) AS searches
FROM n
WHERE org_name IN {IMMIGRATION_ORGS}
GROUP BY org_name, reason
ORDER BY org_name, searches DESC
"""

# Every row the false-positive review removed, in full -- printed so the
# exclusion stays an auditable step, not a silent filter.
EXCLUDED_ROWS_QUERY = f"""
{NETWORK_CTE}
SELECT org_name, reason, COUNT(*) AS searches
FROM n
WHERE {IMMIGRATION_TERMS} AND {FALSE_POSITIVES}
  AND org_name NOT IN {IMMIGRATION_ORGS}
GROUP BY org_name, reason
ORDER BY searches DESC
"""

# The denominator shown in the bottom panel's title: all outside-agency
# searches through networks including Kenner's cameras in 2025 (Kenner
# also appears in its own network audit; excluded as everywhere in this
# repo).
NETWORK_TOTAL_QUERY = """
SELECT COUNT(*) FROM network_audit
WHERE search_time >= '2025-01-01' AND search_time < '2026-01-01'
  AND org_name != 'Kenner LA PD'
"""


def top_examples(pairs_by_key, max_items):
    """{key: [reason, ...]} keeping the query's per-key order."""
    examples = {}
    for key, reason in pairs_by_key:
        examples.setdefault(key, [])
        if len(examples[key]) < max_items:
            examples[key].append(reason)
    return examples


def format_examples(reasons, max_len=24):
    """Quote and truncate example reasons for the right-hand column."""
    parts = []
    for reason in reasons:
        if len(reason) > max_len:
            reason = reason[:max_len - 1] + "…"
        parts.append(f"'{reason}'")
    return ", ".join(parts)


def build_figure(categories, counts, category_examples,
                 agencies, agency_counts, agency_examples, network_total):
    """Two stacked panels: Kenner's own reason buckets on top (blue,
    immigration highlighted in rust), the top outside agencies using
    Kenner's network for immigration below (rust). Bars occupy the left
    two thirds; the right column shows example raw reasons per bar."""
    total = sum(counts)
    imm_total = sum(agency_counts)
    n_agencies = len(agencies)
    top_agencies = agencies[:TOP_AGENCIES]
    top_counts = agency_counts[:TOP_AGENCIES]

    fig = make_subplots(
        rows=2, cols=1, vertical_spacing=0.10,
        row_heights=[0.42, 0.58],
        subplot_titles=(
            "What Kenner PD said its 38,037 searches were for",
            f"Top {TOP_AGENCIES} of {n_agencies} agencies that searched"
            " the network for immigration"
            f"<br><sup>{imm_total:,} immigration searches, out of"
            f" {network_total:,} outside-agency searches in 2025</sup>",
        ),
    )
    # Subplot titles span the full figure width by default; re-center
    # them over the bar area so they don't collide with the example
    # column on the right.
    for subplot_title in fig.layout.annotations:
        subplot_title.update(x=0.33, xanchor="center")

    colors = [HIGHLIGHT_COLOR if c == HIGHLIGHT_CATEGORY else BAR_COLOR
              for c in categories]
    labels = [f"{n:,} ({n / total:.1%})" if n / total >= 0.001
              else f"{n:,} (<0.1%)" for n in counts]
    fig.add_trace(go.Bar(
        x=counts, y=categories, orientation="h",
        marker_color=colors,
        text=labels, textposition="outside",
        textfont=dict(size=12),
        hovertemplate="%{y}: %{x:,} searches<extra></extra>",
    ), row=1, col=1)

    fig.add_trace(go.Bar(
        x=top_counts, y=top_agencies, orientation="h",
        marker_color=HIGHLIGHT_COLOR,
        text=[f"{n:,}" for n in top_counts], textposition="outside",
        textfont=dict(size=12),
        hovertemplate="%{y}: %{x:,} immigration searches<extra></extra>",
    ), row=2, col=1)

    fig.update_layout(
        title=dict(
            text="Kenner PD's Flock cameras in 2025: what Kenner searched"
                 " for, and who searched them for immigration"
                 "<br><sup>Top: officer-typed 'reason' on Kenner PD's own"
                 " 38,037 searches, grouped into buckets (rules in the"
                 " README); 44% gave a generic or vague reason.</sup>"
                 "<br><sup>Bottom: outside-agency searches through"
                 " networks including Kenner's cameras that were"
                 " immigration-related. Right column: most-typed raw"
                 " 'reason' strings per row.</sup>",
        ),
        showlegend=False,
        width=1240, height=1430,
        margin=dict(l=310, b=210, t=150),
    )
    # Bars keep the left two thirds; the right third is the example
    # column, drawn as annotations below.
    fig.update_xaxes(domain=[0, 0.66], separatethousands=True,
                     range=[0, max(counts) * 1.22], row=1, col=1)
    fig.update_xaxes(domain=[0, 0.66],
                     title=dict(text="Searches in 2025"),
                     separatethousands=True,
                     range=[0, max(top_counts) * 1.17], row=2, col=1)
    fig.update_yaxes(autorange="reversed", row=1, col=1)
    fig.update_yaxes(autorange="reversed", row=2, col=1)

    example_font = dict(size=10.5, color="#666")
    header_font = dict(size=11, color="#444")
    for panel_yref, keys, examples in (
            ("y", categories, category_examples),
            ("y2", top_agencies, agency_examples)):
        for key in keys:
            fig.add_annotation(
                text=format_examples(examples.get(key, [])),
                xref="paper", x=0.685, xanchor="left",
                yref=panel_yref, y=key,
                showarrow=False, font=example_font,
            )
    # One column header per panel, aligned with the example column.
    for header_y in (1.0, 0.527):
        fig.add_annotation(
            text="<i>Example reasons (as typed)</i>",
            xref="paper", x=0.685, xanchor="left",
            yref="paper", y=header_y, yanchor="bottom",
            showarrow=False, font=header_font,
        )

    fig.add_annotation(
        text="11 searches assisting HSI (ICE's investigative arm)",
        x=0, y=categories.index(HIGHLIGHT_CATEGORY),
        xanchor="left", xshift=120, showarrow=True, arrowhead=2,
        ax=60, ay=0, font=dict(size=11, color=HIGHLIGHT_COLOR),
        row=1, col=1,
    )
    # The formula, as a legend-style box below the bottom panel: quiet
    # background matching the plot surface, left-aligned with the
    # source block.
    fig.add_annotation(
        text="<b>Counted as an immigration search:</b> the typed reason"
             " contains HSI, whole-word ICE or ERO, 'immigr…',"
             " 'deport…' or 'alien'."
             "<br>Or the search was run"
             " by HSI / US Border Patrol themselves.",
        xref="paper", yref="paper", x=0, y=-0.045,
        xanchor="left", yanchor="top", align="left",
        showarrow=False, font=dict(size=10.5, color="#555"),
        bgcolor="#e5ecf6", bordercolor="#c8d4e3",
        borderwidth=1, borderpad=8,
    )
    fig.add_annotation(
        text=f"…plus {n_agencies - TOP_AGENCIES} more agencies with"
             f" {sum(agency_counts[TOP_AGENCIES:]):,} immigration searches",
        xref="paper", yref="paper", x=0.645, y=0.065, xanchor="right",
        showarrow=False, font=dict(size=11, color="#666"),
    )
    fig.add_annotation(
        text="Source: public record request (Flock organization + network"
             " audits, Jan-Dec 2025):"
             '<br><a href="https://www.muckrock.com/foi/kenner-16256/'
             'public-records-request-flock-audits-201972/">'
             "https://www.muckrock.com/foi/kenner-16256/"
             "public-records-request-flock-audits-201972/</a>"
             "<br>More info on the methodology on"
             ' <a href="https://github.com/eye-on-surveillance/'
             'foia-flock-kenner">github.com/eye-on-surveillance</a>',
        xref="paper", yref="paper", x=0, y=-0.115,
        xanchor="left", yanchor="top", align="left",
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
    rows = connection.execute(CATEGORY_QUERY).fetchall()
    category_example_rows = connection.execute(
        CATEGORY_EXAMPLES_QUERY).fetchall()
    immigration_detail = connection.execute(
        IMMIGRATION_DETAIL_QUERY).fetchall()
    agency_rows = connection.execute(AGENCY_QUERY).fetchall()
    agency_example_rows = connection.execute(
        AGENCY_EXAMPLES_QUERY).fetchall()
    fed_example_rows = connection.execute(FED_EXAMPLES_QUERY).fetchall()
    excluded_rows = connection.execute(EXCLUDED_ROWS_QUERY).fetchall()
    network_total = connection.execute(NETWORK_TOTAL_QUERY).fetchone()[0]
    connection.close()

    categories = [row[0] for row in rows]
    counts = [row[1] for row in rows]
    total = sum(counts)

    print(f"{'category':<30} {'searches':>9}")
    for category, count in rows:
        print(f"{category:<30} {count:>9,}")
    print(f"{'TOTAL':<30} {total:>9,}")

    # Verification 1: the buckets must add up exactly to the known 2025
    # total -- otherwise the CASE dropped or double-counted rows.
    if total != EXPECTED_TOTAL:
        print(f"\nERROR: buckets sum to {total}, expected"
              f" {EXPECTED_TOTAL}; not writing outputs.", file=sys.stderr)
        sys.exit(1)
    print(f"\nVerification: buckets sum to expected {EXPECTED_TOTAL} OK")

    # Every raw reason the immigration arm matched, in full -- read this
    # to confirm nothing unrelated slipped into the highlighted bucket.
    print("\nRaw reasons in the immigration bucket (Kenner's own searches):")
    for reason, count in immigration_detail:
        print(f"  {reason!r}: {count}")

    agencies = [row[0] for row in agency_rows]
    agency_counts = [row[1] for row in agency_rows]
    imm_total = sum(agency_counts)

    # Verification 2: the per-agency rows must add up exactly to the
    # known immigration-connected total.
    if imm_total != EXPECTED_IMMIGRATION_TOTAL:
        print(f"\nERROR: agency rows sum to {imm_total}, expected"
              f" {EXPECTED_IMMIGRATION_TOTAL}; not writing outputs.",
              file=sys.stderr)
        sys.exit(1)
    print(f"\nVerification: agency rows sum to expected"
          f" {EXPECTED_IMMIGRATION_TOTAL} OK")

    # Verification 3: the denominator shown in the bottom panel's title.
    if network_total != EXPECTED_NETWORK_TOTAL:
        print(f"\nERROR: network total is {network_total}, expected"
              f" {EXPECTED_NETWORK_TOTAL}; not writing outputs.",
              file=sys.stderr)
        sys.exit(1)
    print(f"Verification: outside-agency total matches expected"
          f" {EXPECTED_NETWORK_TOTAL} OK")

    # Every network-audit row the false-positive review removed -- read
    # this to confirm only the documented non-agency phrases were
    # dropped (see the table in README.md).
    print(f"\nRows excluded as false positives"
          f" ({sum(r[2] for r in excluded_rows)} searches):")
    for org, reason, count in excluded_rows:
        print(f"  {org} | {reason!r}: {count}")

    print(f"\nAll {len(agencies)} agencies with immigration-related"
          f" searches through Kenner's network in 2025"
          f" (top {TOP_AGENCIES} shown in the chart):")
    for org, count in agency_rows:
        print(f"  {org:<55} {count:>6,}")

    category_examples = top_examples(
        [(cat, reason) for cat, reason, _ in category_example_rows],
        max_items=3)
    agency_examples = top_examples(
        [(org, reason) for org, reason, _ in agency_example_rows],
        max_items=2)
    # HSI / Border Patrol: counted by agency, examples from what they
    # actually typed.
    agency_examples.update(top_examples(
        [(org, reason) for org, reason, _ in fed_example_rows],
        max_items=2))

    fig = build_figure(categories, counts, category_examples,
                       agencies, agency_counts, agency_examples,
                       network_total)
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
