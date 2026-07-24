# /// script
# requires-python = ">=3.10"
# dependencies = ["plotly", "kaleido"]
# ///
"""Graph: what the US Postal Inspection Service searches Kenner's cameras for.

Reads:  cache/flock.db  (build it with the setup-scripts/ pipeline first)
Writes: next to this script, in results/usps-deep-dive/:
        usps_deep_dive.html  (interactive, self-contained)
        usps_deep_dive.svg
        usps_deep_dive.png

Why this graph: USPIS ran 52,572 searches touching Kenner's cameras in
full months alone (Jan 2024 - Dec 2025) -- more than the other 12
federal agencies combined -- all under a single, fully redacted user
identity, with a total pause from Jul 18 2024 to Apr 3 2025. After
Jun 23 2025 it is the only federal agency still searching. This script
breaks down the free-text 'reason' field to show what USPIS says it is
searching for, with special attention to immigration-related reasons.

January 2026 is excluded throughout: the FOIA response only covers it
through Jan 16, and a partial month would distort both the category
shares and the monthly stack.

The 'reason' column is the only usable text field for USPS rows:
'filters' is redacted ('***') or empty, 'text_prompt' and 'moderation'
are empty on all rows, and every user name is redacted.

How reasons are classified (ordered rules, first match wins; the
normalized form is lowercased, trimmed, quotes stripped):
1. The immigration-explicit reasons, matched exactly:
   'Immigration (civil/administrative) - PHX2500025I', 'ERO MKE
   suspect', 'USPIS/HSI Investigation'.
2. Non-reasons, matched exactly: 'test', 'Daytime search for best
   result', 'Image Download', 'Practice on my vehicle', 'Training'.
3. A small table of exact abbreviations ('MF' -> financial fraud,
   'CI'/'Inv'/'Inquiry'/... -> generic investigation, 'BOLO'/'Arrest'
   -> fugitive).
4. Case-number-only patterns (e.g. '3922491', '4222212-MT',
   '281W-WF-3860365', 'MT-4141874'): bucket 'case number only'; the
   letter suffixes/prefixes (MT, PMN, ROBB, MF...) are USPIS program
   codes and are tallied in the audit output.
5. Keyword categories, in order: mail theft; narcotics/drugs; robbery
   (incl. carriers and arrow/castle keys); burglary; check & financial
   fraud; violence/threats; fugitive/locate/task force; generic
   investigation; suspect/vehicle lookup; stolen (other).
6. Everything else stays 'other / unclassified' (7.2%) and is printed
   verbatim -- deliberately no guessing: e.g. the searches whose reason
   is just 'HS' are left unclassified rather than read as 'Homeland
   Security'.

Published outputs show categories only; the raw reasons (which
occasionally name individual suspects) appear only in this script's
printed audit, and the immigration-explicit reasons quoted on the chart
contain no personal names.

Idempotent: re-running overwrites the three output files.
"""

import re
import sqlite3
import sys
from pathlib import Path

import plotly.graph_objects as go
from plotly.subplots import make_subplots

OUTPUT_DIR = Path(__file__).resolve().parent      # results/usps-deep-dive
PROJECT_ROOT = OUTPUT_DIR.parent.parent
DB_FILE = PROJECT_ROOT / "cache" / "flock.db"
OUTPUT_BASENAME = "usps_deep_dive"

ORG = "[Federal] US Postal Inspection Service"

# In-data timeline facts (verified; the pause check below re-derives them).
PAUSE_LAST = "2024-07-18"    # last search before the pause
PAUSE_FIRST = "2025-04-03"   # first search after the pause
HSI_LAST = "2025-05-01"      # Homeland Security Investigations cut off
USBP_LAST = "2025-06-23"     # US Border Patrol cut off -> USPIS sole federal
# External report (NOT from the FOIA data; shown as a dashed line):
# Washington Post, Apr 29 2025: USPIS joined a DHS immigration task force.
WAPO_DATE = "2025-04-29"

# Frozen classification totals, full months only (sum = 52,572). Any
# drift -- new data or an accidental change to the rules -- fails the run.
EXPECTED_CATEGORIES = {
    "case number only": 10_901,
    "mail theft": 10_241,
    "generic investigation": 9_345,
    "narcotics / drugs": 5_413,
    "other / unclassified": 3_808,
    "fugitive / locate / task force": 2_807,
    "suspect / vehicle lookup": 2_716,
    "robbery (incl. carriers)": 2_589,
    "check & financial fraud": 2_498,
    "stolen (other)": 727,
    "burglary": 627,
    "non-reasons": 489,
    "violence / threats": 406,
    "immigration-explicit": 5,
}
EXPECTED_TOTAL = 52_572

# The chart covers the 24 complete months, Jan 2024 - Dec 2025 (same
# cutoff as results/internal-vs-network/).
LAST_FULL_MONTH = "2025-12"

IMMIGRATION = {"immigration (civil/administrative) - phx2500025i",
               "ero mke suspect", "uspis/hsi investigation"}
NON_REASONS = {"test", "daytime search for best result", "image download",
               "practice on my vehicle", "training"}
EXACT = {"mf": "check & financial fraud", "ci": "generic investigation",
         "inv": "generic investigation", "inv.": "generic investigation",
         "invest": "generic investigation", "inquiry": "generic investigation",
         "criminal": "generic investigation", "crim inv": "generic investigation",
         "interview": "generic investigation", "ci2": "generic investigation",
         "bolo": "fugitive / locate / task force",
         "arrest": "fugitive / locate / task force"}
CASE_RES = [re.compile(r"^\d{6,8}\s*[-–— ]?\s*[a-z]{0,4}$"),
            re.compile(r"^\d{3}[a-z]-[a-z]{2}-\d{7}$"),
            re.compile(r"^[a-z]{1,4}-?\d{6,8}$"),
            re.compile(r"^[a-z]{2,4}-\d{2}-\d{4}$")]
RULES = [
    ("mail theft",
     ["mail theft", "mailtheft", "mail thief", "stolen mail", " mt ",
      "mt suspect"]),
    ("narcotics / drugs",
     ["narcotic", "natcotic", "narc", "drug", "pmn", "meth", "fentanyl",
      "marijuana", "parcel", "m30"]),
    ("robbery (incl. carriers)",
     ["robbery", "robber", "robbed", "carrier", "arrow key", "castle key"]),
    ("burglary", ["burglar", " burg ", "breaking"]),
    ("check & financial fraud",
     ["check", "money order", "fraud", "treasury", "identity",
      "counterfeit", "snap", "financial", "scam", "mule", "embezzl"]),
    ("violence / threats",
     ["workplace violence", "wpv", "assault", "threat", "shooting",
      "homicide"]),
    ("fugitive / locate / task force",
     ["fugitive", "locate", "wanted", "warrant", "apprehension",
      "task force", "tfo", "usms", "attempt to"]),
    ("generic investigation",
     ["investigation", "investigative", "inspectigation", "inspectiga",
      "general search", "criminal inv", "intel", "surveillance", "follow",
      "research", "case", "subject identification"]),
    ("suspect / vehicle lookup",
     ["suspect", "vehicle", " veh", " auto ", "plate", "atl"]),
    ("stolen (other)", ["stolen", "theft", "stole"]),
]

MONTHLY_REASONS = """
SELECT reason, substr(search_time, 1, 7) AS month, COUNT(*) AS searches
FROM network_audit
WHERE org_name = ? AND substr(search_time, 1, 7) <= ?
GROUP BY reason, month
"""

CATEGORY_COLORS = {  # distinct hues so stack segments are easy to tell
    # apart; no editorial emphasis, just separability. Every category
    # gets its own entry (not just the current top 8) so a future data
    # update that reorders the ranking can't crash on a missing color.
    "case number only": "#4a5867",              # dark slate (opaque)
    "mail theft": "#3182bd",                    # blue
    "generic investigation": "#8c564b",         # brown
    "narcotics / drugs": "#2ca02c",             # green
    "other / unclassified": "#b3b3b3",          # gray
    "fugitive / locate / task force": "#9467bd",  # purple
    "check & financial fraud": "#17becf",       # cyan
    "suspect / vehicle lookup": "#ff7f0e",      # orange
    "robbery (incl. carriers)": "#e377c2",      # pink
    "stolen (other)": "#bcbd22",                # olive
    "burglary": "#c49c94",                      # tan
    "non-reasons": "#f7b6d2",                   # light pink
    "violence / threats": "#ffbb78",            # light orange
    "immigration-explicit": "#aec7e8",          # light blue
    "everything else": "#e5d9c3",               # pale sand
}


def classify(reason):
    """Ordered rules from the module docstring; returns a category name."""
    norm = reason.lower().strip().strip("\"“”‘’'")
    if norm in IMMIGRATION:
        return "immigration-explicit"
    if norm in NON_REASONS:
        return "non-reasons"
    if norm in EXACT:
        return EXACT[norm]
    if any(pattern.match(norm) for pattern in CASE_RES):
        return "case number only"
    padded = " " + norm + " "
    for category, keywords in RULES:
        if any(keyword in padded for keyword in keywords):
            return category
    return "other / unclassified"


def case_suffix(reason):
    """Program code of a case-number-only reason ('4222212-MT' -> 'MT')."""
    letters = re.sub(r"[^A-Za-z]", "", reason).upper()
    return letters or "(none)"


def build_figure(category_totals, monthly, months, total):
    """Panel 1: category bars. Panel 2: monthly stack with the timeline."""
    fig = make_subplots(
        rows=2, cols=1, vertical_spacing=0.15, row_heights=[0.42, 0.58],
        subplot_titles=(
            "What USPIS gave as the reason (share of 52,572 searches)",
            "USPIS searches per month, stacked by reason category",
        ),
    )

    # Panel 1: every category, largest on top.
    ordered = sorted(category_totals, key=category_totals.get)
    fig.add_trace(go.Bar(
        y=ordered, x=[category_totals[c] for c in ordered],
        orientation="h", marker_color="#4f7ca6",
        text=[f"{category_totals[c]:,} ({100 * category_totals[c] / total:.1f}%)"
              for c in ordered],
        textposition="outside", textfont=dict(size=10),
        hovertemplate="%{y}: %{x:,} searches<extra></extra>",
        showlegend=False,
    ), row=1, col=1)
    fig.update_xaxes(range=[0, 13_500], row=1, col=1,
                     separatethousands=True)

    # Panel 2: stacked months; the 8 biggest categories plus one grouped
    # remainder, so the stack stays readable.
    stack_cats = sorted(category_totals, key=category_totals.get,
                        reverse=True)[:8]
    rest = [c for c in category_totals if c not in stack_cats]
    for category in stack_cats + ["everything else"]:
        if category == "everything else":
            values = [sum(monthly.get((c, m), 0) for c in rest)
                      for m in months]
        else:
            values = [monthly.get((category, m), 0) for m in months]
        fig.add_trace(go.Bar(
            x=months, y=values, name=category,
            marker_color=CATEGORY_COLORS[category],
            hovertemplate="%{x} — " + category +
                          ": %{y:,}<extra></extra>",
        ), row=2, col=1)
    fig.update_layout(barmode="stack")
    fig.update_xaxes(tickformat="%b %Y", dtick="M3",
                     range=["2023-12-10", "2025-12-25"], row=2, col=1)
    # Peaks reach ~4,500; the extra headroom is a clear band where the
    # event labels can sit without touching any bar.
    fig.update_yaxes(separatethousands=True, range=[0, 6_200], row=2, col=1)

    # Timeline marks on panel 2. Solid = facts in this dataset;
    # dashed = an external press report, labeled as such. Labels anchored
    # so each flows into empty space (the pause gap or the headroom band).
    events = [
        (PAUSE_LAST, "pause: last search Jul 18, 2024", 0.97, "left"),
        (PAUSE_FIRST, "searches resume Apr 3, 2025", 0.90, "right"),
        (HSI_LAST, "HSI cut off May 1, 2025", 0.74, "right"),
        (USBP_LAST, "USBP cut off Jun 23, 2025:<br>USPIS now the only"
                    " federal agency searching", 0.97, "left"),
    ]
    for date, label, y, anchor in events:
        fig.add_shape(type="line", x0=date, x1=date, y0=0, y1=1,
                      xref="x2", yref="y2 domain",
                      line=dict(color="#555555", width=1))
        fig.add_annotation(x=date, y=y, xref="x2", yref="y2 domain",
                           text=label, showarrow=False, xanchor=anchor,
                           xshift=4 if anchor == "left" else -4,
                           align=anchor,
                           font=dict(size=9, color="#555555"))
    fig.add_shape(type="line", x0=WAPO_DATE, x1=WAPO_DATE, y0=0, y1=1,
                  xref="x2", yref="y2 domain",
                  line=dict(color="#999999", width=1, dash="dot"))
    fig.add_annotation(x=WAPO_DATE, y=0.82, xref="x2", yref="y2 domain",
                       text="Apr 29, 2025: Washington Post reports USPIS"
                            " joined a DHS<br>immigration task force"
                            " (external report, not from this dataset)",
                       showarrow=False, xanchor="right", xshift=-4,
                       align="right", font=dict(size=9, color="#999999"))

    fig.update_layout(
        title=dict(
            text="The US Postal Inspection Service on Kenner's cameras:"
                 " 52,572 searches, one redacted identity"
                 "<br><sup>Reasons given are dominated by mail theft,"
                 " opaque case numbers, and generic 'investigation';"
                 " narcotics is the #2 substantive category.</sup>"
                 "<br><sup>Explicitly immigration-related reasons: 5 of"
                 " 52,572 ('ERO MKE suspect', 'USPIS/HSI"
                 " Investigation').</sup>"
                 "<br><sup>But ~21% bare case numbers and ~18% generic"
                 " reasons mean the reason field cannot rule out other"
                 " uses. Full months only: Jan 2024 - Dec 2025.</sup>",
            yref="container", y=0.985, yanchor="top",
        ),
        legend=dict(orientation="h", y=-0.04, yanchor="top", x=0,
                    font=dict(size=10)),
        width=1100, height=1050,
        margin=dict(t=140, b=230),
    )
    fig.add_annotation(
        text="Source: public record request (Flock audit logs,"
             " full months only Jan 2024 - Dec 2025, USPIS rows only):"
             ' <a href="https://www.muckrock.com/foi/kenner-16256/'
             'public-records-request-flock-audits-201972/">'
             "https://www.muckrock.com/foi/kenner-16256/"
             "public-records-request-flock-audits-201972/</a>"
             "<br>Categories are keyword groupings of the free-text"
             " 'reason' field; full rules and every unclassified reason:"
             " this folder's script."
             "<br>More info on the methodology on"
             ' <a href="https://github.com/eye-on-surveillance/'
             'foia-flock-kenner">github.com/eye-on-surveillance</a>',
        xref="paper", yref="paper", x=0, y=-0.17,
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
    rows = connection.execute(MONTHLY_REASONS, (ORG, LAST_FULL_MONTH)).fetchall()
    pause = connection.execute(
        "SELECT MAX(CASE WHEN search_time < '2025-01' THEN search_time END),"
        "       MIN(CASE WHEN search_time > '2024-08' THEN search_time END)"
        " FROM network_audit WHERE org_name = ?", (ORG,)).fetchone()
    connection.close()

    category_totals, monthly, case_suffixes = {}, {}, {}
    unclassified, reason_totals = [], {}
    for reason, month, count in rows:
        category = classify(reason)
        category_totals[category] = category_totals.get(category, 0) + count
        monthly[(category, month)] = monthly.get((category, month), 0) + count
        reason_totals[reason] = reason_totals.get(reason, 0) + count
        if category == "case number only":
            suffix = case_suffix(reason)
            case_suffixes[suffix] = case_suffixes.get(suffix, 0) + count
    unclassified = [(c, r) for r, c in reason_totals.items()
                    if classify(r) == "other / unclassified"]
    total = sum(category_totals.values())

    # Verification: frozen totals and the pause boundaries must match.
    print("Verification: classification vs frozen figures")
    all_ok = total == EXPECTED_TOTAL
    print(f"  total: {total:,} expected {EXPECTED_TOTAL:,}"
          f" {'OK' if all_ok else 'MISMATCH'}")
    for category, expected in EXPECTED_CATEGORIES.items():
        got = category_totals.get(category, 0)
        ok = got == expected
        all_ok &= ok
        print(f"  {category}: {got:,} expected {expected:,}"
              f" {'OK' if ok else 'MISMATCH'}")
    pause_ok = (pause[0][:10], pause[1][:10]) == (PAUSE_LAST, PAUSE_FIRST)
    all_ok &= pause_ok
    print(f"  pause: {pause[0][:10]} -> {pause[1][:10]}"
          f" {'OK' if pause_ok else 'MISMATCH'}")
    if not all_ok:
        print("\nERROR: figures do not match; not writing outputs.",
              file=sys.stderr)
        sys.exit(1)

    print("\nCase-number program codes (top 12):")
    for suffix, count in sorted(case_suffixes.items(),
                                key=lambda kv: -kv[1])[:12]:
        print(f"  {count:>7,}  {suffix}")

    months = sorted({m for _, m, _ in rows})
    print("\nPre-pause vs post-pause composition:")
    pre = {c: sum(v for (cat, m), v in monthly.items()
                  if cat == c and m <= "2024-07") for c in category_totals}
    post = {c: sum(v for (cat, m), v in monthly.items()
                   if cat == c and m >= "2025-04") for c in category_totals}
    pre_total, post_total = sum(pre.values()), sum(post.values())
    print(f"  {'category':<32} {'pre':>7} {'pre%':>6} {'post':>7} {'post%':>6}")
    for c in sorted(category_totals, key=category_totals.get, reverse=True):
        print(f"  {c:<32} {pre[c]:>7,} {100*pre[c]/pre_total:>5.1f}%"
              f" {post[c]:>7,} {100*post[c]/post_total:>5.1f}%")

    print(f"\nUnclassified reasons ({len(unclassified)} distinct,"
          f" {sum(c for c, _ in unclassified):,} searches) — top 40:")
    for count, reason in sorted(unclassified, reverse=True)[:40]:
        print(f"  {count:>6,}  {reason!r}")

    fig = build_figure(category_totals, monthly, months, total)
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
