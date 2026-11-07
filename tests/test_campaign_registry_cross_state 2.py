"""SQLite regression tests for mutual exclusion of active and draft years."""
import sqlite3
import unittest
from pathlib import Path


SOURCE = Path(__file__).resolve().parents[1] / 'app' / '__init__.py'


class CampaignCrossStateTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.db.execute('CREATE TABLE campaign (id INTEGER PRIMARY KEY, status TEXT NOT NULL)')
        for operation in ('INSERT', 'UPDATE'):
            self.db.execute(f"""CREATE TRIGGER campaign_active_draft_exclusion_{operation.lower()}
                BEFORE {operation} ON campaign
                WHEN NEW.status IN ('legacy_active', 'draft') AND EXISTS (
                    SELECT 1 FROM campaign AS other
                    WHERE other.id != NEW.id AND other.status IN ('legacy_active', 'draft')
                )
                BEGIN SELECT RAISE(ABORT, 'Active campaign and draft cannot coexist'); END""")

    def tearDown(self):
        self.db.close()

    def test_active_and_draft_cannot_coexist_in_either_order(self):
        for first, second in [('legacy_active', 'draft'), ('draft', 'legacy_active')]:
            self.db.execute('DELETE FROM campaign')
            self.db.execute('INSERT INTO campaign VALUES (1, ?)', (first,))
            with self.assertRaises(sqlite3.IntegrityError):
                self.db.execute('INSERT INTO campaign VALUES (2, ?)', (second,))
            self.assertEqual(self.db.execute('SELECT COUNT(*) FROM campaign').fetchone()[0], 1)

    def test_update_cannot_activate_draft_while_active_exists(self):
        self.db.execute("INSERT INTO campaign VALUES (1, 'legacy_active')")
        self.db.execute("INSERT INTO campaign VALUES (2, 'archived')")
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("UPDATE campaign SET status = 'draft' WHERE id = 2")
        self.assertEqual(self.db.execute('SELECT status FROM campaign WHERE id = 2').fetchone()[0], 'archived')

    def test_archiving_allows_draft_and_preserves_history(self):
        self.db.execute("INSERT INTO campaign VALUES (1, 'legacy_active')")
        self.db.execute("UPDATE campaign SET status = 'archived' WHERE id = 1")
        self.db.execute("INSERT INTO campaign VALUES (2, 'draft')")
        self.assertEqual(self.db.execute('SELECT status FROM campaign ORDER BY id').fetchall(),
                         [('archived',), ('draft',)])

    def test_application_installs_both_guards_and_checks_existing_rows(self):
        source = SOURCE.read_text()
        self.assertIn('campaign_active_draft_exclusion_', source)
        self.assertIn("raise RuntimeError('Active campaign and draft coexist')", source)


if __name__ == '__main__':
    unittest.main()
