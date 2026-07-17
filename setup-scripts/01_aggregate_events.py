"""Stage 1: aggregate the raw Event Logs into cache/events.csv.

Reads:  raw-response/Flock Data/Event Logs/event-logs.csv
Writes: cache/events.csv  (one physical line per record, header included)

Run from anywhere:  python3 setup-scripts/01_aggregate_events.py
"""

import csv
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from csv_helpers import escape_newlines, strip_header

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_FILE = PROJECT_ROOT / "raw-response" / "Flock Data" / "Event Logs" / "event-logs.csv"
OUT_FILE = PROJECT_ROOT / "cache" / "events.csv"

# Known-good total, established by hand earlier in this project.
EXPECTED_ROWS = 2_983

OUTPUT_COLUMNS = [
    "event_id",
    "timestamp",
    "user",
    "event_type",
    "entity_type",
    "entity_details",
]


def main():
    rows_read = 0
    newline_escaped_fields = 0
    event_type_counts = Counter()

    OUT_FILE.parent.mkdir(exist_ok=True)
    with open(RAW_FILE, newline="", encoding="utf-8") as raw, \
         open(OUT_FILE, "w", newline="", encoding="utf-8") as out:
        reader = csv.DictReader(raw)
        reader.fieldnames = strip_header(reader.fieldnames)
        writer = csv.writer(out, lineterminator="\n")
        writer.writerow(OUTPUT_COLUMNS)

        print(f"Reading {RAW_FILE.name} ...", flush=True)
        for row in reader:
            rows_read += 1

            # Collapse whitespace in User: raw data has both a leading space
            # (" Casey Smith") and doubled internal spaces ("Ismael  Cornejo");
            # left alone these would count as different users later.
            user = " ".join(row["User"].split())

            details = escape_newlines(row["Entity Details"])
            if details != row["Entity Details"]:
                newline_escaped_fields += 1

            event_type_counts[row["Event Type"]] += 1

            writer.writerow([
                row["Event Id"],
                row["Timestamp"],   # already ISO 8601 with milliseconds
                user,
                row["Event Type"],
                row["Entity Type"],
                details,
            ])
        print(f"  {rows_read} rows")

    if rows_read != EXPECTED_ROWS:
        print(f"ERROR: read {rows_read} rows, expected exactly {EXPECTED_ROWS}. "
              "The raw data changed or the parser is broken. Nothing to trust "
              "downstream until this is explained.", file=sys.stderr)
        sys.exit(1)

    print()
    print(f"Total rows written:            {rows_read} (matches expected {EXPECTED_ROWS})")
    print(f"Fields with escaped newlines:  {newline_escaped_fields}")
    print("Event types:")
    for event_type, count in event_type_counts.most_common():
        print(f"  {event_type}: {count}")
    print(f"\nWrote {OUT_FILE}")


if __name__ == "__main__":
    main()
