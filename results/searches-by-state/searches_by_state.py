# /// script
# requires-python = ">=3.10"
# dependencies = ["plotly", "kaleido"]
# ///
"""Map: searches of Kenner's Flock cameras, by the searching agency's state.

Reads:  cache/flock.db  (build it with the setup-scripts/ pipeline first)
Writes: next to this script, in results/searches-by-state/:
        searches_by_state.html  (interactive, self-contained)
        searches_by_state.svg
        searches_by_state.png

The database is the single source of data: one SQL query plus the
state-detection rules below are the whole calculation, and the script
prints the full per-state table, every ambiguous name, and every
unattributed agency, so the map can be checked end to end.

Run from anywhere:  uv run results/searches-by-state/searches_by_state.py
(uv installs plotly and kaleido from the header above; see README.)

How an agency's state is detected (ordered rules, first match wins).
The export has no state column; the state is parsed from the agency
name, `TRIM(org_name)`, Kenner's own rows excluded:

1. Names starting with the literal prefix '[Federal]' are federal
   agencies, not states: excluded from the map, counted in the footer.
   (Only the bracket prefix counts: 'Federal Way WA PD' and 'Federal
   Heights CO PD' are city agencies and fall through to rule 2.)
2. Two-letter state-code token: last \\b-delimited uppercase match of
   the 50 states + DC anywhere in the name ('Cobb County GA PD' -> GA).
   Last-wins resolves 'CO' meaning "County" ('Blaine CO OK SO' -> OK).
   Exception: a trailing 'SD' with a different code earlier means
   "Sheriff's Department", not South Dakota -- take the earlier code
   ('San Diego County CA SD' -> CA). Every name containing two
   different codes is printed by this script.
3. Full state name, case-insensitive, on word boundaries, longest name
   first (so 'West Virginia' wins over 'Virginia', and 'Kansas' cannot
   match inside 'Arkansas'): 'Kansas Highway Patrol' -> KS.
4. Anything else stays UNATTRIBUTED -- deliberately no guessing and no
   hand-maintained lookup table. These are mostly genuinely multi-state
   bodies (regional intelligence centers, railroads, NCMEC) plus a few
   ambiguous names; together 0.29% of searches. All are printed.

This is a share-of-total chart, not a time series, so it uses the full
data range including the partial last month (Jan 1 2024 - Jan 16 2026).
The red dot marks Kenner, LA itself -- where the searched cameras are.

Idempotent: re-running overwrites the three output files.
"""

import re
import sqlite3
import sys
from pathlib import Path

import plotly.graph_objects as go

OUTPUT_DIR = Path(__file__).resolve().parent      # results/searches-by-state
PROJECT_ROOT = OUTPUT_DIR.parent.parent
DB_FILE = PROJECT_ROOT / "cache" / "flock.db"
OUTPUT_BASENAME = "searches_by_state"

# Known figures the detection must reproduce exactly (verified when this
# graph was built); any drift fails the run instead of drawing a wrong map.
EXPECTED_TOTAL = 10_261_956        # all searches by outside agencies
EXPECTED_FEDERAL = 64_382          # rule 1
EXPECTED_UNATTRIBUTED = 29_513     # rule 4
EXPECTED_ATTRIBUTED = 10_168_061   # rules 2+3 (= total - federal - unattr.)
EXPECTED_TX = 2_688_062            # largest state, sanity anchor

STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut",
    "DE": "Delaware", "FL": "Florida", "GA": "Georgia", "HI": "Hawaii",
    "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa",
    "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine",
    "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan",
    "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri",
    "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico",
    "NY": "New York", "NC": "North Carolina", "ND": "North Dakota",
    "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania",
    "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota",
    "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont",
    "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia",
}
CODE_RE = re.compile(r"\b(" + "|".join(STATES) + r")\b")
# longest first, so 'West Virginia' is tried before 'Virginia'
NAMES_LONGEST_FIRST = sorted(
    ((name.upper(), code) for code, name in STATES.items()),
    key=lambda pair: len(pair[0]), reverse=True)

# Map legend classes: (lower bound, label, fill color). White = zero;
# log-ish steps so Texas (2.69M) cannot wash out the small states.
BINS = [
    (0, "0", "#ffffff"),
    (1, "1 - 10k", "#d4e2ee"),
    (10_000, "10k - 100k", "#a9c6dd"),
    (100_000, "100k - 500k", "#7b9cba"),
    (500_000, "500k - 1M", "#4f7ca6"),
    (1_000_000, "1M+", "#1f4e79"),
]

AGENCY_COUNTS = """
SELECT TRIM(org_name) AS agency, COUNT(*) AS searches
FROM network_audit
WHERE org_name != 'Kenner LA PD'
GROUP BY agency
"""


def detect_state(agency):
    """Apply the ordered rules from the module docstring.

    Returns ('FEDERAL', rule), (state_code, rule), or (None, 'unmatched').
    """
    if agency.startswith("[Federal]"):
        return "FEDERAL", "1 federal prefix"
    codes = CODE_RE.findall(agency)
    if codes:
        if codes[-1] == "SD" and any(c != "SD" for c in codes[:-1]):
            # trailing 'SD' = "Sheriff's Department", not South Dakota
            code = [c for c in codes if c != "SD"][-1]
        else:
            code = codes[-1]
        return code, "2 code token"
    upper = agency.upper()
    for name, code in NAMES_LONGEST_FIRST:
        if re.search(r"\b" + re.escape(name) + r"\b", upper):
            return code, "3 state name"
    return None, "unmatched"


def bin_index(searches):
    """Index into BINS for a state's search count."""
    index = 0
    for i, (lower, _, _) in enumerate(BINS):
        if searches >= lower:
            index = i
    return index


def build_figure(state_searches, state_agencies, total, federal, unattributed):
    """Choropleth with one discrete color class per BINS entry."""
    codes = sorted(STATES)
    z = [bin_index(state_searches.get(c, 0)) for c in codes]
    customdata = [
        (STATES[c], state_searches.get(c, 0), state_agencies.get(c, 0),
         100 * state_searches.get(c, 0) / total)
        for c in codes
    ]
    # stepwise colorscale: each class is a flat color band
    n = len(BINS)
    colorscale = []
    for i, (_, _, color) in enumerate(BINS):
        colorscale += [(i / n, color), ((i + 1) / n, color)]

    fig = go.Figure(go.Choropleth(
        locations=codes, locationmode="USA-states",
        z=z, zmin=-0.5, zmax=n - 0.5,
        colorscale=colorscale,
        marker_line_color="#999999", marker_line_width=0.7,
        customdata=customdata,
        hovertemplate="%{customdata[0]}<br>"
                      "%{customdata[1]:,} searches"
                      " (%{customdata[3]:.1f}% of all outside searches)<br>"
                      "%{customdata[2]:,} agencies<extra></extra>",
        colorbar=dict(
            title=dict(text="Searches by<br>that state's<br>agencies"),
            tickvals=list(range(n)),
            ticktext=[label for _, label, _ in BINS],
            len=0.7,
        ),
    ))

    # Kenner itself: a red dot where the searched cameras actually are.
    fig.add_trace(go.Scattergeo(
        lon=[-90.2417], lat=[29.9941],
        mode="markers+text",
        marker=dict(size=9, color="#c0392b",
                    line=dict(width=1.5, color="white")),
        text=["Kenner"], textposition="bottom right",
        textfont=dict(size=11, color="#c0392b"),
        hovertemplate="Kenner, LA — the searched cameras<extra></extra>",
        showlegend=False,
    ))

    fig.update_layout(
        title=dict(
            text="Who searches Kenner's Flock cameras: searches by the"
                 " agency's home state"
                 "<br><sup>10.26M searches by 5,254 outside agencies,"
                 " Jan 1 2024 - Jan 16 2026. State parsed from the agency"
                 " name (99.1% of searches attributed).</sup>"
                 "<br><sup>Texas alone: 2.69M searches (26%), driven by"
                 " Houston PD (1.01M) and Dallas PD (0.88M).</sup>",
        ),
        geo=dict(scope="usa", lakecolor="white"),
        width=1000, height=650,
        margin=dict(t=110, b=110),
    )
    fig.add_annotation(
        text="Source: public record request (Flock audit logs"
             " Jan 2024 - Jan 16 2026, Kenner's own searches excluded):"
             '<br><a href="https://www.muckrock.com/foi/kenner-16256/'
             'public-records-request-flock-audits-201972/">'
             "https://www.muckrock.com/foi/kenner-16256/"
             "public-records-request-flock-audits-201972/</a>"
             f"<br>Not on the map: 13 federal agencies ({federal:,}"
             f" searches) and 40 multi-state or unidentifiable agencies"
             f" ({unattributed:,} searches, 0.3%)."
             "<br>More info on the methodology on"
             ' <a href="https://github.com/eye-on-surveillance/'
             'foia-flock-kenner">github.com/eye-on-surveillance</a>',
        xref="paper", yref="paper", x=0, y=-0.16,
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
    rows = connection.execute(AGENCY_COUNTS).fetchall()
    connection.close()

    state_searches, state_agencies = {}, {}
    federal = unattributed = 0
    rule_agencies, rule_searches = {}, {}
    multi_code, unmatched_list = [], []
    for agency, count in rows:
        state, rule = detect_state(agency)
        rule_agencies[rule] = rule_agencies.get(rule, 0) + 1
        rule_searches[rule] = rule_searches.get(rule, 0) + count
        if len(set(CODE_RE.findall(agency))) > 1:
            multi_code.append((agency, state))
        if state == "FEDERAL":
            federal += count
        elif state is None:
            unattributed += count
            unmatched_list.append((count, agency))
        else:
            state_searches[state] = state_searches.get(state, 0) + count
            state_agencies[state] = state_agencies.get(state, 0) + 1

    total = sum(count for _, count in rows)
    attributed = sum(state_searches.values())

    # Verification: the detection must reproduce the known figures
    # exactly -- otherwise the map silently drifted from the database.
    print("Verification: detection result vs known figures")
    checks = [
        ("total searches", total, EXPECTED_TOTAL),
        ("federal (rule 1)", federal, EXPECTED_FEDERAL),
        ("state-attributed (rules 2+3)", attributed, EXPECTED_ATTRIBUTED),
        ("unattributed (rule 4)", unattributed, EXPECTED_UNATTRIBUTED),
        ("Texas", state_searches.get("TX", 0), EXPECTED_TX),
    ]
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

    print("\nRule coverage (agencies / searches):")
    for rule in sorted(rule_agencies):
        print(f"  rule {rule}: {rule_agencies[rule]:,} agencies,"
              f" {rule_searches[rule]:,} searches")

    print("\nNames containing two different state codes (resolution):")
    for agency, state in sorted(multi_code):
        print(f"  -> {state}  {agency!r}")

    print("\nPer-state table:")
    print(f"  {'state':<6} {'searches':>10} {'agencies':>9}  bin")
    for code in sorted(state_searches, key=state_searches.get, reverse=True):
        searches = state_searches[code]
        print(f"  {code:<6} {searches:>10,} {state_agencies[code]:>9,}"
              f"  {BINS[bin_index(searches)][1]}")
    zero_states = sorted(set(STATES) - set(state_searches))
    print(f"  zero searches ({len(zero_states)}): {', '.join(zero_states)}")

    print(f"\nUnattributed agencies ({len(unmatched_list)}):")
    for count, agency in sorted(unmatched_list, reverse=True):
        print(f"  {count:>7,}  {agency!r}")

    fig = build_figure(state_searches, state_agencies, total,
                       federal, unattributed)
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
