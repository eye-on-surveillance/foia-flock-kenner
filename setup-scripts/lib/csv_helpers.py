"""Small pure helper functions shared by the 01_aggregate_*.py scripts.

Every function here takes plain values in and returns plain values out --
no file access, no global state. Each docstring contains a runnable
example; you can verify all of them at once with:

    python3 -m doctest setup-scripts/lib/csv_helpers.py -v
"""

from datetime import datetime

# The one known non-numeric value in "Total Devices Searched": two em-dash
# characters (U+2014 U+2014), no space. See step-one-data-transform.txt,
# review addendum, amendment 2.
EM_DASH_SENTINEL = "——"


def strip_header(fieldnames):
    """Remove the stray leading/trailing spaces from raw CSV column names.

    Every column except "ID" in the audit files has a leading space
    (e.g. " Name", " Org Name").

    >>> strip_header(['ID', ' Name', ' Org Name'])
    ['ID', 'Name', 'Org Name']
    """
    return [name.strip() for name in fieldnames]


def parse_audit_timestamp(raw):
    """Convert the audit files' US-style timestamp to ISO 8601 (UTC).

    >>> parse_audit_timestamp('01/25/2024, 01:27:03 PM UTC')
    '2024-01-25T13:27:03Z'
    """
    parsed = datetime.strptime(raw.strip(), "%m/%d/%Y, %I:%M:%S %p UTC")
    return parsed.strftime("%Y-%m-%dT%H:%M:%SZ")


def split_time_frame(raw):
    """Split the two-line "Time Frame" field into (start, end), both ISO 8601.

    Every audit row has exactly one embedded newline in this field
    (verified across 100% of rows in both audit sources). Anything else
    is a real anomaly, so this raises instead of guessing.

    >>> split_time_frame('01/22/2024, 06:00:00 AM UTC\\n01/22/2024, 07:00:00 AM UTC')
    ('2024-01-22T06:00:00Z', '2024-01-22T07:00:00Z')
    """
    parts = raw.split("\n")
    if len(parts) != 2:
        raise ValueError(
            "Time Frame did not contain exactly 2 lines: %r" % (raw,)
        )
    return parse_audit_timestamp(parts[0]), parse_audit_timestamp(parts[1])


def parse_nullable_int(raw):
    """Parse a numeric field that may contain the em-dash sentinel.

    Returns a (value, category) pair so the caller can count what it saw:
      - a plain integer        -> (the int, 'ok')
      - the em-dash sentinel   -> (None, 'sentinel')   known Flock quirk
      - anything else          -> (None, 'unexpected') should never happen;
        a non-zero 'unexpected' count in a script summary means something
        new is wrong with the data.

    >>> parse_nullable_int('2394')
    (2394, 'ok')
    >>> parse_nullable_int('——')
    (None, 'sentinel')
    >>> parse_nullable_int('N/A')
    (None, 'unexpected')
    """
    text = raw.strip()
    if text == EM_DASH_SENTINEL:
        return None, "sentinel"
    try:
        return int(text), "ok"
    except ValueError:
        return None, "unexpected"


def escape_newlines(raw):
    r"""Replace literal newlines inside a field with the two characters \n.

    This is what guarantees the aggregated CSVs have exactly one physical
    line per record, so `wc -l` and `grep` work as expected on them.
    Documented in DATA_DICTIONARY.md under "known data quirks".

    >>> escape_newlines('line one\nline two')
    'line one\\nline two'
    """
    return raw.replace("\r\n", "\\n").replace("\n", "\\n").replace("\r", "\\n")


def monthly_sort_key(filename):
    """Sort key (year, month) for the monthly audit file names.

    >>> monthly_sort_key('10_1_2024-10_31_2024-Kenner LA PD-Audit.csv')
    (2024, 10)
    >>> monthly_sort_key('2_1_2025-2_28_2025-Kenner LA PD-Audit.csv')
    (2025, 2)
    """
    month, _day, year = filename.split("-")[0].split("_")
    return (int(year), int(month))
