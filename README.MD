# Analysis of FOIA request response for Flock usage in Kenner, Louisiana

This repository exposes reproducible analysis around this FOIA request:
https://www.muckrock.com/foi/kenner-16256/public-records-request-flock-audits-201972/

The raw data and the artifacts built from it are not stored in git.
You download the former and rebuild the latter. 

| Folder | Role |
|---|---|
| `raw-response/` | the FOIA content, untouched (downloaded, not in git) |
| `setup-scripts/` | code that builds everything else from the raw input |
| `cache/` | generated artifacts: aggregated CSVs + `flock.db` (rebuilt, not in git) |
| `results/` | human-friendly outputs (graphs, tables) |

Requirements: Python 3.8+ with SQLite 3.37+ 
 The graph scripts use plotly and run via [uv](https://docs.astral.sh/uv/), which handles their dependencies.

## Obtain the public records request results

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
python3 setup-scripts/00_download_foia_result.py
```

Expected output:

```
Downloading https://cdn.muckrock.com/foia_files/2026/02/26/2-3-26_MR201972.zip (509 MiB) ...
  done
Verifying md5 ...
  OK (facee13f82244fd5e7c2180bc0d3899b)
Extracting into .../raw-response ...
  52 files extracted
```

Either way, the zip md5sum must be: `facee13f82244fd5e7c2180bc0d3899b`

## What the raw data should look like

Before going further, check that `raw-response/` matches this layout
(`tree raw-response`) — the scripts below expect exactly these paths:

```
raw-response
├── 2-3-26 MR201972.pdf
├── Flock Data
│   ├── Event Logs
│   │   └── event-logs.csv
│   ├── Network Audit
│   │   ├── 1_1_2024-1_31_2024-Kenner LA PD-Network-Audit.csv
│   │   ├── ...
│   │   └── 9_1_2025-9_30_2025-Kenner LA PD-Network-Audit.csv
│   └── Organization Audit
│       ├── 1_1_2024-1_31_2024-Kenner LA PD-Audit.csv
│       ├── ...
│       └── 9_1_2025-9_30_2025-Kenner LA PD-Audit.csv
└── README.md
```

Network Audit and Organization Audit hold one file per month, Jan 2024
through Jan 2026, 25 each. Quick check:

```
find raw-response -name '*.csv' | wc -l    # 51
```

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

One CSV per month is not practical, Step 01
aggregates each source into a single clean CSV in `cache/`, one line per
record. Each script prints its own audit trail and exits with an error if
any count is off; compare yours against the expected outputs below.

```
python3 setup-scripts/01_aggregate_events.py
```

Expected output:

```
Reading event-logs.csv ...
  2983 rows

Total rows written:            2983 (matches expected 2983)
Fields with escaped newlines:  2983
Event types:
  create: 1407
  update: 861
  delete: 715
```

```
python3 setup-scripts/01_aggregate_org_audit.py
```

Expected output:

```
Reading 1_1_2024-1_31_2024-Kenner LA PD-Audit.csv ... 3359 rows
...
Reading 1_1_2026-1_16_2026-Kenner LA PD-Audit.csv ... 1059 rows

Total rows written:              66933 (matches expected 66933)
Duplicate IDs (kept, see docs):  409
'——' sentinels -> NULL:          5376
Unexpected non-numeric values:   0
Rows with *** redaction:         0
Fields with escaped newlines:    0
Search types:
  search: 51104
  lookup: 15584
  freeform: 245
```

```
python3 setup-scripts/01_aggregate_network_audit.py   # 10.3M rows, takes a few minutes
```

Expected output:

```
Reading 1_1_2024-1_31_2024-Kenner LA PD-Network-Audit.csv ... 200859 rows
...
Reading 1_1_2026-1_16_2026-Kenner LA PD-Network-Audit.csv ... 280822 rows

Total rows written:              10327835 (matches expected 10327835)
Duplicate IDs (kept, see docs):  62965
'——' sentinels -> NULL:          693860
Unexpected non-numeric values:   0
Rows with *** redaction:         10261956
Fields with escaped newlines:    102
Search types:
  lookup: 7949983
  search: 2358940
  convoy: 17898
  visual: 445
  freeform: 417
  multiGeo: 152
```

Independent check:

```
wc -l cache/events.csv           # 2984
wc -l cache/org_audit.csv        # 66934
wc -l cache/network_audit.csv    # 10327836
```

## Build a SQLite database

Step 02 loads the three CSVs into `cache/flock.db` (STRICT tables, typed
columns, no further transformation):

```
python3 setup-scripts/02_load_sqlite.py
```

Expected output:

```
Loading events.csv into events ...
  2983 rows loaded
Loading org_audit.csv into org_audit ...
  66933 rows loaded
Loading network_audit.csv into network_audit ...
  10327835 rows loaded

Verification: CSV record count vs SELECT COUNT(*)
  events: csv=2983 db=2983 OK
  org_audit: csv=66933 db=66933 OK
  network_audit: csv=10327835 db=10327835 OK
```
Manual check:
```
python3 -m sqlite3 cache/flock.db "SELECT search_type, COUNT(*) FROM org_audit GROUP BY search_type;"
# freeform|245  lookup|15584  search|51104
```

## Graphs

Each graph lives in its own folder under `results/`, holding the script
that computes it and everything it produces: a self-contained interactive
HTML page and static SVG/PNG images. The scripts read `cache/flock.db` --
the database is the single source of data, and each script prints the
numbers it plots so a chart can be checked by re-running its SQL queries.
Unlike the pipeline, they use an external library (plotly), so they are
run with `uv`, which reads each script's dependency header and installs
what it needs on first run:

```
uv run results/internal-vs-network/internal_vs_network.py
```

Each script prints the numbers it plots plus a totals check against the
known row counts, and fails instead of drawing a wrong chart. Charts use
full months only (Jan 2024 - Dec 2025); January 2026 is excluded because
the FOIA response only covers it through Jan 16.

One-time setup: plotly's image exporter (kaleido) needs a Chrome binary
and will say so if it can't find one. Fetch a private headless copy with:

```
uv run --with kaleido python -c "import kaleido; kaleido.get_chrome_sync()"
```

Expected output of `internal_vs_network.py`:

```
Verification: monthly buckets vs known totals
  internal (org_audit): total=65874 expected=65874 OK
  external (network_audit minus Kenner): total=9979019 expected=9979019 OK

month    kenner_internal external_network
2024-01            3,359          195,848
...
2025-12            3,363          531,363

Wrote .../results/internal-vs-network/internal_vs_network.html
Wrote .../results/internal-vs-network/internal_vs_network.svg
Wrote .../results/internal-vs-network/internal_vs_network.png
```
