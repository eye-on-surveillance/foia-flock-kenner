# Analysis of FOIA request response for Flock usage in Kenner, Louisiana

This repository exposes reproducible analysis around this FOIA request:
https://www.muckrock.com/foi/kenner-16256/public-records-request-flock-audits-201972/

The raw data and the artifacts built from it are not stored in git.
You download the former and rebuild the latter. 

| Folder | Role |
|---|---|
| `raw-response/` | the FOIA content, untouched (downloaded, not in git) |
| `script/` | code that builds everything else from the raw input |
| `cache/` | generated artifacts: aggregated CSVs + `flock.db` (rebuilt, not in git) |
| `results/` | human-friendly outputs (graphs, tables) |

Requirements: Python 3.8+ with SQLite 3.37+ (`python3 -c "import sqlite3; print(sqlite3.sqlite_version)"`).
No external libraries.

## Obtain the FOIA results

Download the zip and verify it:

```
curl -fLO https://cdn.muckrock.com/foia_files/2026/02/26/2-3-26_MR201972.zip \
  && echo "facee13f82244fd5e7c2180bc0d3899b  2-3-26_MR201972.zip" | md5sum -c \
  && unzip -q 2-3-26_MR201972.zip -d raw-response \
  && mv "raw-response/2-3-26 MR201972/"* raw-response/ \
  && rmdir "raw-response/2-3-26 MR201972"
```

This is for a fresh setup (the `mv` would nest `Flock Data` if it already
exists). 


Or, as a convenience step, this script does the same download, checksum,
and extraction, and can be re-run safely:

```
python3 script/00_download_foia_result.py
```

Either way, the zip md5sum must be: `facee13f82244fd5e7c2180bc0d3899b`

## Understanding the FOIA response : What's inside?

The response contains three folders under `Flock Data/` for Kenner LA PD, Jan 2024 - Jan 2026:

- `Event Logs/` - 1 file, 2,983 rows. Administrative actions in Kenner's
  Flock account (hotlist edits, settings), not searches.
- `Organization Audit/` - 25 monthly files, 66,933 rows. Searches run by
  Kenner PD's own users.
- `Network Audit/` - 25 monthly files, 10,327,835 rows. Searches run by
  other agencies whose search included Kenner's cameras.

see `DATA_DICTIONARY.md` for detail.

## Aggregate the results to work with them

One CSV per month is not practical, and a small DB is handy. Step 01
aggregates each source into a single clean CSV in `cache/`, one line per
record:

```
python3 script/01_aggregate_events.py
python3 script/01_aggregate_org_audit.py
python3 script/01_aggregate_network_audit.py   # 10.3M rows, takes a few minutes
```

check yourself

```
wc -l cache/events.csv           # 2984
wc -l cache/org_audit.csv        # 66934
wc -l cache/network_audit.csv    # 10327836
```

## Build a SQLite database

Step 02 loads the three CSVs into `cache/flock.db` (STRICT tables, typed
columns, no further transformation):

```
python3 script/02_load_sqlite.py
```

The script re-counts each CSV and asserts it equals `SELECT COUNT(*)` per
table. Manual check, no install needed:

```
python3 -m sqlite3 cache/flock.db "SELECT search_type, COUNT(*) FROM org_audit GROUP BY search_type;"
# freeform|245  lookup|15584  search|51104
```
