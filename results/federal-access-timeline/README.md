This graph shows every U.S. federal agency that ever searched Kenner's Flock cameras, and when: one row per agency, running from its first search to its last.

## How the numbers were built

Flock's export doesn't have a "is this a federal agency" column, but any agency whose name in the export starts with the literal tag `[Federal]` (for example `[Federal] US Postal Inspection Service`, `[Federal] US Border Patrol [Inactive]`) is treated as federal. 

For each federal agency, every day it ran at least one search becomes a dot on that agency's row; the dot's size shows how many searches happened that day. A line connects the first dot to the last, so the row reads left-to-right as "how long was this agency active."

Six of the thirteen federal accounts also carry a second tag from Flock, `[Inactive]`. That's a fact Flock recorded, not something inferred from the data — so it's marked with its own symbol (a red X on the agency's last search) rather than being folded into "this agency looks like it stopped." An agency can stop searching without ever being tagged `[Inactive]`, and the chart is careful to show that difference: the tag means "Flock says this account is inactive," the absence of later dots just means "no searches after this date happened to appear in this export."

## Worked example

`[Federal] US Border Patrol [Inactive]` has 209 searches, its first on May 9, 2025 and its last on June 23, 2025. Because its name carries Flock's `[Inactive]` tag, June 23 is marked with a red X. `[Federal] US GSA Office of Inspector General` also stopped, on March 26, 2025 — but its name has no `[Inactive]` tag, so that date gets a plain gray label instead of a red X: the data shows it stopped, but Flock never marked it inactive.

## Full detail

The full agency list, exact counts, and the reasoning behind every visual choice live in `federal_access_timeline.py` in this folder.
