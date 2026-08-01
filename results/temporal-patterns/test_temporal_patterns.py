"""Tests for the tricky parts of temporal_patterns.py: timezone
conversion and the Kenner exclusion filter.

Uses an in-memory SQLite database — no FOIA data download required.
"""

import sqlite3
import unittest

from temporal_patterns import query_heatmap_data, QUERY_TEMPLATE


def _make_test_db():
    """Create an in-memory SQLite database with known search timestamps."""
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE org_audit (search_time TEXT NOT NULL, org_name TEXT NOT NULL)")
    conn.execute("CREATE TABLE network_audit (search_time TEXT NOT NULL, org_name TEXT NOT NULL)")

    # Known timestamps (UTC) -> Central Time (UTC-6):
    #   Mon 20:00 UTC -> Mon 14:00 CT  (hour shifts)
    #   Mon 20:30 UTC -> Mon 14:30 CT  (same slot, two searches)
    #   Tue 03:00 UTC -> Mon 21:00 CT  (day shifts backward across midnight)
    conn.executemany(
        "INSERT INTO org_audit (search_time, org_name) VALUES (?, ?)",
        [
            ("2024-01-15T20:00:00Z", "Kenner LA PD"),
            ("2024-01-15T20:30:00Z", "Kenner LA PD"),
            ("2024-01-16T03:00:00Z", "Kenner LA PD"),
        ],
    )
    conn.executemany(
        "INSERT INTO network_audit (search_time, org_name) VALUES (?, ?)",
        [
            ("2024-01-15T20:00:00Z", "Houston TX PD"),
            ("2024-01-15T20:00:00Z", "Dallas TX PD"),
            ("2024-01-15T20:00:00Z", "Kenner LA PD"),  # should be excluded
        ],
    )
    return conn


class TestTimezoneConversion(unittest.TestCase):
    def setUp(self):
        self.conn = _make_test_db()
        self.query = QUERY_TEMPLATE.format(table="org_audit", where="")

    def tearDown(self):
        self.conn.close()

    def test_hour_shifts_utc_to_central(self):
        """Mon 20:00 UTC -> Mon 14:00 CT. Two searches land in same slot."""
        grid, _ = query_heatmap_data(self.conn, self.query)
        self.assertEqual(grid[0][14], 2)  # Mon=0, hour 14

    def test_day_shifts_across_midnight(self):
        """Tue 03:00 UTC -> Mon 21:00 CT. Day shifts backward."""
        grid, _ = query_heatmap_data(self.conn, self.query)
        self.assertEqual(grid[0][21], 1)  # Mon=0, hour 21


class TestKennerExclusion(unittest.TestCase):
    def setUp(self):
        self.conn = _make_test_db()

    def tearDown(self):
        self.conn.close()

    def test_excludes_kenner_from_network_audit(self):
        query = QUERY_TEMPLATE.format(table="network_audit", where="WHERE org_name != 'Kenner LA PD'")
        _, total = query_heatmap_data(self.conn, query)
        self.assertEqual(total, 2)  # Houston + Dallas, not Kenner


if __name__ == "__main__":
    unittest.main()
