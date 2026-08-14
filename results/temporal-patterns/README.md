Two side-by-side heatmaps showing *when* Flock searches happen — hour of day and day of week — for Kenner PD vs. outside agencies.

Concentrated blocks reveal human-driven searches (officers on shift). Uniform spread reveals automated surveillance.

## How the numbers were built

Each search timestamp is converted from UTC to Central Time, then counted into one of 168 hour×day slots. Kenner PD's own searches (66,933) appear on the left; every other agency (10,261,956) on the right.

The script prints summary statistics — business hours, overnight, and weekend percentages — so the patterns are quotable, not just visual.

## Full detail

See `temporal_patterns.py` in this folder.
