# /// script
# requires-python = ">=3.10"
# dependencies = ["plotly", "kaleido"]
# ///
"""Graph: timeline of every federal agency that searched Kenner's cameras.

Reads:  cache/flock.db  (build it with the setup-scripts/ pipeline first)
Writes: next to this script, in results/federal-access-timeline/:
        federal_access_timeline.html  (interactive, self-contained)
        federal_access_timeline.svg
        federal_access_timeline.png

The database is the single source of data: the one SQL query below is
the whole calculation, and the script prints every agency's totals and
first/last search dates, so the chart can be checked by re-running the
query against cache/flock.db.

Run from anywhere:  uv run results/federal-access-timeline/federal_access_timeline.py
(uv installs plotly and kaleido from the header above; see README.)

Definitions -- see DATA_DICTIONARY.md:
- "Federal agency" = network_audit rows whose org_name starts with
  '[Federal]'. That prefix, and the '[Inactive]' tag on 6 of the 13
  accounts, are Flock's own labels in the FOIA export of February 2026.
  The chart strips the prefix and shows the tag as a dagger to reduce
  noise; the table this script prints keeps every org_name verbatim.
- One chart row per agency: a line spanning first to last search, a dot
  per day with at least one search (dot size = searches that day). Every
  agency that stopped is annotated with its last search date; a red x
  additionally marks the 6 accounts Flock tagged [Inactive], keeping the
  explicit tag distinct from a mere absence of searches.
- Kenner's event logs contain no grant/revocation entries for any
  federal agency, so each agency's LAST SEARCH DATE plus the
  '[Inactive]' tag is the only available evidence of when its network
  access ended.
- Unlike the monthly graphs, the partial month January 2026 is kept:
  this chart shows spans, not per-month volumes, and cutting the axis
  at Dec 2025 would hide that the US Postal Inspection Service is still
  searching right up to the last day of data (Jan 16, 2026).

Idempotent: re-running overwrites the three output files.
"""

import math
import sqlite3
import sys
from pathlib import Path

import plotly.graph_objects as go

OUTPUT_DIR = Path(__file__).resolve().parent    # results/federal-access-timeline
PROJECT_ROOT = OUTPUT_DIR.parent.parent
DB_FILE = PROJECT_ROOT / "cache" / "flock.db"
OUTPUT_BASENAME = "federal_access_timeline"

DATA_END = "2026-01-16"  # last day covered by the FOIA response

# Every agency expected in the data with its total search count
# (verified against the db when this graph was built). The script fails
# if an agency appears/disappears or any count changes, so the chart can
# never silently drift from the database.
EXPECTED_TOTALS = {
    "[Federal] ATF Louisville KY [inactive]": 1_824,
    "[Federal] ATF Nashville TN [inactive]": 7_387,
    "[Federal] Homeland Security Investigations [Inactive]": 175,
    "[Federal] Lake Mead NV NRA": 14,
    "[Federal] Langley VA Air Force Base": 220,
    "[Federal] National Park Service TN [Inactive]": 61,
    "[Federal] Naval Criminal Investigative Service [Inactive]": 171,
    "[Federal] Roudebush Medical Center IN Veterans Affairs PD": 6,
    "[Federal] US Border Patrol [Inactive]": 209,
    "[Federal] US GSA Office of Inspector General": 255,
    "[Federal] US Park Police - Chattahoochee River NRA": 3,
    "[Federal] US Postal Inspection Service": 54_035,
    "[Federal] Wright Patterson OH Air Force Base": 22,
}  # sums to 64,382

DOT_COLOR = "#5d84a6"        # steel blue, same for every agency
LAST_SEARCH_COLOR = "#c0392b"

# search_time is ISO-8601 text ('2025-06-05T14:02:11Z'), so its first
# 10 characters are the day, 'YYYY-MM-DD'. substr() keeps the grouping
# trivially checkable against the raw strings.
DAILY_BY_AGENCY = """
SELECT org_name, substr(search_time, 1, 10) AS day, COUNT(*) AS searches
FROM network_audit
WHERE org_name LIKE '[Federal]%'
GROUP BY org_name, day
ORDER BY org_name, day
"""


def daily_counts(connection):
    """Run the query; returns {org_name: {day: count}}."""
    per_org = {}
    for org, day, count in connection.execute(DAILY_BY_AGENCY):
        per_org.setdefault(org, {})[day] = count
    return per_org


def check_totals(per_org):
    """Print one audit line per agency; returns True when all match."""
    all_ok = True
    for org in sorted(set(EXPECTED_TOTALS) | set(per_org)):
        expected = EXPECTED_TOTALS.get(org)
        total = sum(per_org.get(org, {}).values())
        ok = expected == total
        all_ok &= ok
        print(f"  {total:>7,} expected {expected or 0:>7,}"
              f" {'OK' if ok else 'MISMATCH'}  {org}")
    return all_ok


def dot_size(count):
    """Dot area conveys searches/day; sqrt keeps 1 and 400 both visible."""
    return min(4 + 2 * math.sqrt(count), 18)


def build_figure(per_org):
    """One row per agency, x = time, sorted so the first agency to stop
    is the top row and the still-active one the bottom row."""
    order = sorted(per_org, key=lambda org: max(per_org[org]))  # by last day
    # Chart labels drop Flock's '[Federal] ' prefix and replace the noisy
    # '[Inactive]' tags with a dagger (explained in the legend); the
    # printed audit table keeps the names verbatim.
    labels = {org: org.removeprefix("[Federal] ")
                     .replace(" [Inactive]", " †")
                     .replace(" [inactive]", " †")
              for org in order}

    fig = go.Figure()
    for org in order:
        days = sorted(per_org[org])
        first, last = days[0], days[-1]
        # span line from first to last search
        fig.add_trace(go.Scatter(
            x=[first, last], y=[labels[org]] * 2, mode="lines",
            line=dict(color="#b8c4cc", width=2),
            hoverinfo="skip", showlegend=False,
        ))
        # one dot per active day, sized by that day's search count
        fig.add_trace(go.Scatter(
            x=days, y=[labels[org]] * len(days), mode="markers",
            marker=dict(size=[dot_size(per_org[org][d]) for d in days],
                        color=DOT_COLOR, opacity=0.75),
            customdata=[per_org[org][d] for d in days],
            hovertemplate="%{y}<br>%{x}: %{customdata:,} searches"
                          "<extra></extra>",
            showlegend=False,
        ))
        # Every agency that stopped shows its last search date; the red x
        # goes ONLY on the 6 accounts Flock tagged [Inactive], so the tag
        # and the mere absence of searches stay visually distinct.
        tagged = "[inactive]" in org.lower()
        if last < DATA_END:
            if tagged:
                fig.add_trace(go.Scatter(
                    x=[last], y=[labels[org]], mode="markers",
                    marker=dict(symbol="x", size=10, color=LAST_SEARCH_COLOR),
                    hovertemplate=f"last search: {last}"
                                  f"<extra>{labels[org]}</extra>",
                    showlegend=False,
                ))
            fig.add_annotation(
                x=last, y=labels[org], text=last, showarrow=False,
                xanchor="left", xshift=10,
                font=dict(size=10, color=LAST_SEARCH_COLOR if tagged
                          else "#5f6a6a"),
            )

    # Size legend: one invisible-data trace per reference count, so the
    # legend shows what a small/medium/large dot means. 50+ because dot
    # size is capped: busier days all render at the maximum size.
    for count, name in ((1, "1 search/day"), (10, "10"), (50, "50+")):
        fig.add_trace(go.Scatter(
            x=[None], y=[None], mode="markers", name=name,
            marker=dict(size=dot_size(count), color=DOT_COLOR, opacity=0.75),
            showlegend=True,
        ))
    # Legend entry for the red x (only on [Inactive]-tagged accounts).
    fig.add_trace(go.Scatter(
        x=[None], y=[None], mode="markers",
        name="last search, account tagged [Inactive] (†)",
        marker=dict(symbol="x", size=10, color=LAST_SEARCH_COLOR),
        showlegend=True,
    ))

    # right edge of the data, so "still active" is visibly different
    # from "stopped"
    fig.add_shape(type="line", x0=DATA_END, x1=DATA_END, y0=-0.5,
                  y1=len(order) - 0.5, line=dict(color="#666", width=1,
                                                 dash="dash"))
    fig.add_annotation(x=DATA_END, y=len(order) - 0.5, text="data ends<br>Jan 16, 2026",
                       showarrow=False, xanchor="left", xshift=6, yanchor="top",
                       font=dict(size=10, color="#666"))

    fig.update_layout(
        title=dict(
            text="Federal agencies searching Kenner's Flock cameras:"
                 " 12 of 13 stopped by mid-2025"
                 "<br><sup>One row per agency; dot size = searches that day."
                 " Agencies that stopped show their last search date; a red"
                 " x marks the 6 accounts tagged [Inactive].</sup>"
                 "<br><sup>Only the US Postal Inspection Service (54,035 of"
                 " the 64,382 federal searches) is still active when the"
                 " data ends.</sup>"
                 "<br><sup>6 of the 13 accounts are tagged [Inactive] in"
                 " the export; all 6 stopped searching, but so did 6"
                 " agencies without the tag.</sup>",
            yref="container", y=0.96, yanchor="top",
        ),
        legend=dict(orientation="h",
                    itemsizing="trace", itemwidth=30,
                    x=1, xanchor="right", y=1.01, yanchor="bottom",
                    font=dict(size=11)),
        xaxis=dict(tickformat="%b %Y", dtick="M3",
                   range=["2023-12-01", "2026-03-25"]),
        # categoryarray runs bottom-up: Postal (still active) at the
        # bottom, first agency to stop at the top.
        yaxis=dict(categoryorder="array",
                   categoryarray=[labels[org] for org in reversed(order)]),
        width=1100, height=700,
        margin=dict(t=150, b=110),
    )
    fig.add_annotation(
        text="Source: this public record request (Flock audit logs"
             " Jan 2024 - Jan 16 2026):"
             ' <a href="https://www.muckrock.com/foi/kenner-16256/'
             'public-records-request-flock-audits-201972/">'
             "https://www.muckrock.com/foi/kenner-16256/"
             "public-records-request-flock-audits-201972/</a>"
             "<br>No grant/revocation events appear in Kenner's event logs;"
             " last search dates and the [Inactive] tags in the export are"
             " the best cutoff evidence."
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
    per_org = daily_counts(connection)
    connection.close()

    # Verification: every agency must match its known total exactly --
    # otherwise the chart silently drifted from the database.
    print("Verification: per-agency totals vs known counts")
    if not check_totals(per_org):
        print("\nERROR: totals do not match; not writing outputs.",
              file=sys.stderr)
        sys.exit(1)

    print("\nTimeline (sorted by last search):")
    print(f"{'first':<12} {'last':<12} {'searches':>9}  agency")
    for org in sorted(per_org, key=lambda o: max(per_org[o])):
        days = sorted(per_org[org])
        print(f"{days[0]:<12} {days[-1]:<12}"
              f" {sum(per_org[org].values()):>9,}  {org}")

    fig = build_figure(per_org)
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
