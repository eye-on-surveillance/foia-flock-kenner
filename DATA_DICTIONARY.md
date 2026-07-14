# Data dictionary

Column-by-column reference for the tables in `cache/flock.db` (the
`cache/*.csv` files have identical columns), plus the known quirks of the
raw data and a glossary. For how to build these files and the high-level
view, see `README.MD`.

## Table: `events` (2,983 rows from `Event Logs/event-logs.csv`)

Administrative actions taken in Kenner PD's Flock account (creating
hotlists, adding plates, changing settings).

| Column | Type | Nullable | Description | Example | Transformation |
|---|---|---|---|---|---|
| `event_id` | TEXT | no (primary key) | Flock's unique id for the event | `fe4502df-3ef8-…` | none |
| `timestamp` | TEXT | no | when the action happened, ISO 8601 UTC with milliseconds | `2026-01-15T18:57:01.323Z` | none (already ISO in the raw file) |
| `user` | TEXT | yes | who did it | `Casey Smith` | whitespace collapsed (see quirks) |
| `event_type` | TEXT | no | what kind of action | `create`, `update`, `delete` | none |
| `entity_type` | TEXT | no | what kind of thing was acted on | `Custom Hotlist Entry` | none |
| `entity_details` | TEXT | yes | free-text description of the thing acted on, as `Key: value` lines | `Hotlist Name: …\nLicense: …` | embedded newlines escaped to literal `\n` (see quirks); **not** parsed into sub-fields in this pass |

## Tables: `org_audit` (66,933 rows) and `network_audit` (10,327,835 rows)

Identical columns; different scope. `org_audit` (from `Organization
Audit/*.csv`) is searches run **by Kenner PD users**. `network_audit`
(from `Network Audit/*.csv`) is searches run by **other agencies** whose
searches included Kenner's cameras.

| Column | Type | Nullable | Description | Example | Transformation |
|---|---|---|---|---|---|
| `id` | TEXT | no — but **not unique** (see quirks) | Flock's id for the search | `ea9acc20-4f96-…` | none |
| `name` | TEXT | yes | person who ran the search | `Billy Hingle`, `***` | kept verbatim, including `***` |
| `name_redacted` | INTEGER | no | 1 iff `name` is exactly `***`, else 0 | `0` | derived convenience flag |
| `org_name` | TEXT | no | agency the searcher belongs to | `Kenner LA PD` | none |
| `total_networks_searched` | INTEGER | yes | how many camera networks the search covered | `83` | clean integer in 100% of raw rows |
| `total_devices_searched` | INTEGER | yes | how many cameras the search covered | `2394` | `——` sentinel → NULL (see quirks) |
| `time_frame_start` | TEXT | yes | start of the time window searched, ISO 8601 UTC | `2024-01-22T06:00:00Z` | first line of the raw two-line "Time Frame" field, reformatted |
| `time_frame_end` | TEXT | yes | end of that window | `2024-01-22T07:00:00Z` | second line, reformatted |
| `license_plate` | TEXT | yes | plate searched for; may contain `*` wildcards | `Z*0028*`, `***` | kept verbatim |
| `license_plate_redacted` | INTEGER | no | 1 iff `license_plate` is exactly `***`, else 0 | `0` | derived convenience flag |
| `reason` | TEXT | yes | free-text reason the searcher typed | `In`, `stolen vehicle` | newlines escaped |
| `case_number` | TEXT | yes | case number the searcher typed (raw column "Case #") | `24-1234` | newlines escaped |
| `filters` | TEXT | yes | vehicle-description filters used | `Pickup, white` | newlines escaped; can also be `***` (see quirks) |
| `search_time` | TEXT | no | when the search was run, ISO 8601 UTC, second precision | `2024-01-25T13:27:03Z` | reformatted from `01/25/2024, 01:27:03 PM UTC` |
| `search_type` | TEXT | no | kind of search | `search`, `lookup`, `freeform` | none |
| `text_prompt` | TEXT | yes | the natural-language prompt, for `freeform` searches | | newlines escaped |
| `moderation` | TEXT | yes | Flock's moderation field for freeform prompts | | newlines escaped |
| `source_file` | TEXT | no | which monthly raw file the row came from | `1_1_2024-1_31_2024-Kenner LA PD-Audit.csv` | added for traceability back to raw-input |

## Known data quirks

- **Duplicate audit `id`s (Flock export bug).** The audit `id` column is
  NOT unique: org audit has 103 ids appearing more than once (409 extra
  rows), network audit has 62,965 duplicate-id rows (~0.6%). Duplicates
  are consecutive records within the same monthly file; most groups are
  byte-identical, a few differ only by ±1 in `total_devices_searched` — a
  live counter caught mid-tick during Flock's export. **All rows are
  kept** (the known-good totals include them); that is why `id` is not a
  primary key. Evidence: `dup-ids.txt` and `duplicated-records.txt` at
  the project root. `events.event_id` IS unique.
- **`——` sentinel.** `Total Devices Searched` sometimes contains two
  em-dash characters (U+2014 U+2014, no space) instead of a number:
  5,376× in org audit, 693,860× (~6.7%) in network audit. Stage 1 turns
  exactly that string into NULL and counts it; any *other* non-numeric
  value is counted in a separate "unexpected" bucket that is currently
  zero — if a run ever reports it non-zero, something new is wrong.
- **`***` means redacted.** Occurs only in `network_audit` (Kenner's own
  org-audit rows are unredacted), in three columns: `name`,
  `license_plate`, and `filters`. The `*_redacted` flags are set iff the
  value is *exactly* `***`, because legitimate wildcard plate searches
  also contain `*` (e.g. `Z*0028*`).
- **Embedded newlines flattened.** In the raw files, every audit record
  spans two physical lines (the "Time Frame" field always contains one
  newline), and some free-text fields (`Reason`, `Entity Details`, …)
  contain more. Stage 1 splits Time Frame into start/end columns and
  replaces every remaining in-field newline with the two-character
  sequence `\n`. Result: in `cache/*.csv`, one physical line = one
  record, so `wc -l` (minus 1 for the header) is an independent row
  count and one `grep` match is one full record. This is a disclosed
  transformation, not a silent one.
- **Leading-space headers.** Every raw audit column name except `ID`
  has a leading space (` Name`, ` Org Name`, …). Stripped in Stage 1.
- **Messy user names in event logs.** The raw `User` field has leading
  spaces (`" John Smith"`) and doubled internal spaces
  (`"John  Smith"`). Stage 1 collapses whitespace so per-user counts
  don't split one person into several.

## Glossary (ALPR / Flock terms)

- **ALPR** — Automated License Plate Reader; Flock's cameras photograph
  plates of passing vehicles and make them searchable.
- **Hotlist** — a list of plates that triggers an alert whenever one of
  them passes a camera. A *custom hotlist* is one an agency maintains
  itself (most `events` rows are hotlist maintenance).
- **networkShare / network** — Flock agencies can share camera access
  with each other; the *network audit* logs outside agencies searching
  networks that include Kenner's cameras.
- **feedView** — viewing the live/recent feed of a camera rather than
  running a search.
- **search / lookup / freeform / convoy / visual / multiGeo**
  (`search_type`) — *search* is the normal parameterized search (plate,
  time window, vehicle filters); *lookup* is a direct plate lookup;
  *freeform* is a natural-language query (see `text_prompt`), which
  Flock passes through `moderation`. Three more types appear only in
  `network_audit`: *convoy* (find vehicles traveling together), *visual*
  (search by vehicle appearance/image), and *multiGeo* (search across
  multiple geographic areas). Kenner's own `org_audit` contains only the
  first three.
