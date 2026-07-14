"""Stage 2: load the cleaned cache/*.csv files into cache/flock.db.

Reads:  cache/events.csv, cache/org_audit.csv, cache/network_audit.csv
Writes: cache/flock.db  (SQLite, STRICT tables)

Run from anywhere:  python3 script/02_load_sqlite.py
Run the three 01_aggregate_*.py scripts first.

This script does ZERO data transformation. every cleaning decision
already happened in Stage 1. Idempotent.
"""

import csv
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CACHE = PROJECT_ROOT / "cache"
DB_FILE = CACHE / "flock.db"

BATCH_SIZE = 10_000

# Event Id is unique across all 2,983 rows, so it is the primary key.
EVENTS_SCHEMA = """
CREATE TABLE events (
    event_id       TEXT PRIMARY KEY,
    timestamp      TEXT NOT NULL,
    user           TEXT,
    event_type     TEXT NOT NULL,
    entity_type    TEXT NOT NULL,
    entity_details TEXT
) STRICT
"""

# The audit "id" column is NOT unique (a Flock export quirk duplicates some
# records -- see DATA_DICTIONARY.md), so it is a plain column, not a primary
# key. The implicit rowid is the row identity. STRICT has no BOOLEAN type;
# the *_redacted flags use the idiomatic INTEGER 0/1.
AUDIT_SCHEMA = """
CREATE TABLE {table} (
    id                      TEXT NOT NULL,
    name                    TEXT,
    name_redacted           INTEGER NOT NULL,
    org_name                TEXT NOT NULL,
    total_networks_searched INTEGER,
    total_devices_searched  INTEGER,
    time_frame_start        TEXT,
    time_frame_end          TEXT,
    license_plate           TEXT,
    license_plate_redacted  INTEGER NOT NULL,
    reason                  TEXT,
    case_number             TEXT,
    filters                 TEXT,
    search_time             TEXT NOT NULL,
    search_type             TEXT NOT NULL,
    text_prompt             TEXT,
    moderation              TEXT,
    source_file             TEXT NOT NULL
) STRICT
"""


def event_row_to_tuple(row):
    """Map one events.csv row (list of strings) to typed column values."""
    return tuple(row)  # all six columns are TEXT


def audit_row_to_tuple(row):
    """Map one org/network_audit.csv row (list of strings) to typed values.

    Only two kinds of mapping happen: the 0/1 flag columns become integers,
    and the numeric columns become integers (or NULL where Stage 1 wrote an
    empty string for the '——' sentinel).
    """
    (row_id, name, name_redacted, org_name, networks, devices,
     start, end, plate, plate_redacted, reason, case_number, filters,
     search_time, search_type, text_prompt, moderation, source_file) = row
    return (
        row_id, name, int(name_redacted), org_name,
        int(networks) if networks else None,
        int(devices) if devices else None,
        start, end, plate, int(plate_redacted), reason, case_number,
        filters, search_time, search_type, text_prompt, moderation,
        source_file,
    )


def load_table(connection, table, csv_path, row_to_tuple):
    """Bulk-insert one CSV into one table; returns the number of rows loaded."""
    print(f"Loading {csv_path.name} into {table} ...", flush=True)
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        placeholders = ",".join("?" * len(header))
        insert = f"INSERT INTO {table} VALUES ({placeholders})"

        loaded = 0
        batch = []
        for row in reader:
            batch.append(row_to_tuple(row))
            if len(batch) >= BATCH_SIZE:
                connection.executemany(insert, batch)
                loaded += len(batch)
                batch = []
        if batch:
            connection.executemany(insert, batch)
            loaded += len(batch)
    connection.commit()
    print(f"  {loaded} rows loaded")
    return loaded


def count_csv_records(csv_path):
    """Independent record count: physical lines minus the header.

    This is exactly `wc -l` minus 1, and it is only valid because Stage 1
    escaped every embedded newline -- one physical line per record.
    """
    with open(csv_path, encoding="utf-8") as f:
        return sum(1 for _ in f) - 1


def main():
    tables = [
        ("events", CACHE / "events.csv", EVENTS_SCHEMA, event_row_to_tuple),
        ("org_audit", CACHE / "org_audit.csv",
         AUDIT_SCHEMA.format(table="org_audit"), audit_row_to_tuple),
        ("network_audit", CACHE / "network_audit.csv",
         AUDIT_SCHEMA.format(table="network_audit"), audit_row_to_tuple),
    ]

    missing = [str(path) for _, path, _, _ in tables if not path.exists()]
    if missing:
        print("ERROR: missing input(s): " + ", ".join(missing) +
              "\nRun the 01_aggregate_*.py scripts first.", file=sys.stderr)
        sys.exit(1)

    connection = sqlite3.connect(DB_FILE)

    for table, csv_path, schema, row_to_tuple in tables:
        connection.execute(f"DROP TABLE IF EXISTS {table}")
        connection.execute(schema)
        load_table(connection, table, csv_path, row_to_tuple)

    # Verification 1: recount each CSV independently (plain line count, not
    # the csv module) and compare with what the database now contains. This
    # separates "did Stage 2 load everything it was given" from "was Stage 1
    # correct" (Stage 1 asserts its own totals).
    print("\nVerification: CSV record count vs SELECT COUNT(*)")
    failed = False
    for table, csv_path, _, _ in tables:
        csv_count = count_csv_records(csv_path)
        db_count = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        status = "OK" if csv_count == db_count else "MISMATCH"
        if csv_count != db_count:
            failed = True
        print(f"  {table}: csv={csv_count} db={db_count} {status}")

    connection.close()

    if failed:
        print("\nERROR: row count mismatch between CSV and database.", file=sys.stderr)
        sys.exit(1)
    print(f"\nWrote {DB_FILE}")


if __name__ == "__main__":
    main()
