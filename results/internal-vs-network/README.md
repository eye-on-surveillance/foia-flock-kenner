This graph compares two things, side by side, every month: how many searches Kenner PD ran on its own Flock cameras, and how many searches every other agency in the country ran that happened to touch Kenner's cameras.

## How the numbers were built

Flock's export splits searches into two separate logs:

- One log of searches run by Kenner PD's own users.
- One log of searches run by *every* agency on the Flock network whose search included Kenner's cameras — Kenner included, since Kenner can also search its own network.

To avoid counting the same search twice, "external" searches are simply everything in the second log that wasn't run by Kenner itself. Both logs are then counted up month by month.

The last month in the data, January 2026, is left out of this graph. The public records request only covers it through January 16, so a half-month would show up as a fake drop in activity — it's not that searches stopped, it's that the data stops.

## Worked example

For June 2025: every row in Kenner's own search log with a June 2025 timestamp is counted (3,665 searches). Separately, every row in the network-wide log with a June 2025 timestamp *and* an agency name other than "Kenner LA PD" is counted (539,640 searches). Those two numbers become one bar and one point on the chart for that month.

## Full detail

The exact queries, the row counts they must match, and the full reasoning live in `internal_vs_network.py` in this folder. 
