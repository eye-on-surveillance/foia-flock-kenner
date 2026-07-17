"""Stage 1: aggregate the raw Organization Audit files into cache/org_audit.csv.

Reads:  raw-response/Flock Data/Organization Audit/*.csv  (25 monthly files)
Writes: cache/org_audit.csv  (one physical line per record, header included)

Run from anywhere:  python3 setup-scripts/01_aggregate_org_audit.py

This file is deliberately near-identical to 01_aggregate_network_audit.py:
"""

import csv
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from csv_helpers import (
    escape_newlines,
    monthly_sort_key,
    parse_audit_timestamp,
    parse_nullable_int,
    split_time_frame,
    strip_header,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "raw-response" / "Flock Data" / "Organization Audit"
OUT_FILE = PROJECT_ROOT / "cache" / "org_audit.csv"

# Known-good total, established by hand earlier in this project.
# NOTE: this count INCLUDES the known duplicate-ID rows (a Flock export
# quirk, see DATA_DICTIONARY.md) -- do not deduplicate.
EXPECTED_ROWS = 66_933

OUTPUT_COLUMNS = [
    "id",
    "name",
    "name_redacted",
    "org_name",
    "total_networks_searched",
    "total_devices_searched",
    "time_frame_start",
    "time_frame_end",
    "license_plate",
    "license_plate_redacted",
    "reason",
    "case_number",
    "filters",
    "search_time",
    "search_type",
    "text_prompt",
    "moderation",
    "source_file",
]


def main():
    rows_read = 0
    newline_escaped_fields = 0
    redacted_rows = 0
    sentinel_count = 0        # "——" in Total Devices Searched (known quirk)
    unexpected_numeric = 0    # any OTHER non-numeric value (should stay 0)
    duplicate_ids = 0
    seen_ids = set()
    search_type_counts = Counter()

    raw_files = sorted((f.name for f in RAW_DIR.glob("*.csv")), key=monthly_sort_key)

    OUT_FILE.parent.mkdir(exist_ok=True)
    with open(OUT_FILE, "w", newline="", encoding="utf-8") as out:
        writer = csv.writer(out, lineterminator="\n")
        writer.writerow(OUTPUT_COLUMNS)

        for filename in raw_files:
            print(f"Reading {filename} ...", end="", flush=True)
            file_rows = 0
            with open(RAW_DIR / filename, newline="", encoding="utf-8") as raw:
                reader = csv.DictReader(raw)
                reader.fieldnames = strip_header(reader.fieldnames)
                for row in reader:
                    file_rows += 1

                    row_id = row["ID"]
                    if row_id in seen_ids:
                        duplicate_ids += 1
                    else:
                        seen_ids.add(row_id)

                    networks, networks_kind = parse_nullable_int(row["Total Networks Searched"])
                    devices, devices_kind = parse_nullable_int(row["Total Devices Searched"])
                    sentinel_count += (networks_kind == "sentinel") + (devices_kind == "sentinel")
                    unexpected_numeric += (networks_kind == "unexpected") + (devices_kind == "unexpected")

                    start, end = split_time_frame(row["Time Frame"])

                    # "***" means redacted by Flock; a redaction flag is derived
                    # but the raw value itself is kept untouched.
                    name_redacted = 1 if row["Name"] == "***" else 0
                    plate_redacted = 1 if row["License Plate"] == "***" else 0
                    if name_redacted or plate_redacted:
                        redacted_rows += 1

                    # Escape embedded newlines in every free-text field so the
                    # output is always one physical line per record.
                    free_text = {}
                    for column in ("Name", "License Plate", "Reason", "Case #",
                                   "Filters", "Text Prompt", "Moderation"):
                        escaped = escape_newlines(row[column])
                        if escaped != row[column]:
                            newline_escaped_fields += 1
                        free_text[column] = escaped

                    search_type_counts[row["Search Type"]] += 1

                    writer.writerow([
                        row_id,
                        free_text["Name"],
                        name_redacted,
                        row["Org Name"],
                        "" if networks is None else networks,
                        "" if devices is None else devices,
                        start,
                        end,
                        free_text["License Plate"],
                        plate_redacted,
                        free_text["Reason"],
                        free_text["Case #"],
                        free_text["Filters"],
                        parse_audit_timestamp(row["Search Time"]),
                        row["Search Type"],
                        free_text["Text Prompt"],
                        free_text["Moderation"],
                        filename,
                    ])
            rows_read += file_rows
            print(f" {file_rows} rows")

    if rows_read != EXPECTED_ROWS:
        print(f"ERROR: read {rows_read} rows, expected exactly {EXPECTED_ROWS}. "
              "The raw data changed or the parser is broken. Nothing to trust "
              "downstream until this is explained.", file=sys.stderr)
        sys.exit(1)

    print()
    print(f"Total rows written:              {rows_read} (matches expected {EXPECTED_ROWS})")
    print(f"Duplicate IDs (kept, see docs):  {duplicate_ids}")
    print(f"'——' sentinels -> NULL:          {sentinel_count}")
    print(f"Unexpected non-numeric values:   {unexpected_numeric}" +
          ("  <-- INVESTIGATE, should be 0" if unexpected_numeric else ""))
    print(f"Rows with *** redaction:         {redacted_rows}")
    print(f"Fields with escaped newlines:    {newline_escaped_fields}")
    print("Search types:")
    for search_type, count in search_type_counts.most_common():
        print(f"  {search_type}: {count}")
    print(f"\nWrote {OUT_FILE}")


if __name__ == "__main__":
    main()
