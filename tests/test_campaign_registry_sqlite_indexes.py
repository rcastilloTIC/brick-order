"""SQLite integration contract for campaign status concurrency indexes."""
import sqlite3
import unittest


class CampaignRegistrySQLiteIndexesTest(unittest.TestCase):
    def test_unique_partial_indexes_reject_duplicate_active_and_draft(self):
        db = sqlite3.connect(':memory:')
        db.execute('CREATE TABLE campaign (id INTEGER PRIMARY KEY, status TEXT NOT NULL)')
        db.execute("CREATE UNIQUE INDEX uq_campaign_single_active ON campaign ((1)) WHERE status = 'legacy_active'")
        db.execute("CREATE UNIQUE INDEX uq_campaign_single_draft ON campaign ((1)) WHERE status = 'draft'")
        db.execute("INSERT INTO campaign (status) VALUES ('legacy_active')")
        with self.assertRaises(sqlite3.IntegrityError):
            db.execute("INSERT INTO campaign (status) VALUES ('legacy_active')")
        db.execute("INSERT INTO campaign (status) VALUES ('draft')")
        with self.assertRaises(sqlite3.IntegrityError):
            db.execute("INSERT INTO campaign (status) VALUES ('draft')")
        db.execute("INSERT INTO campaign (status) VALUES ('archived')")
        db.execute("INSERT INTO campaign (status) VALUES ('archived')")
        db.close()

    def test_existing_corrupt_registry_fails_migration(self):
        db = sqlite3.connect(':memory:')
        db.execute('CREATE TABLE campaign (id INTEGER PRIMARY KEY, status TEXT NOT NULL)')
        db.executemany('INSERT INTO campaign (status) VALUES (?)', [('draft',), ('draft',)])
        with self.assertRaises(sqlite3.IntegrityError):
            db.execute("CREATE UNIQUE INDEX uq_campaign_single_draft ON campaign ((1)) WHERE status = 'draft'")
        db.close()

    def test_status_guards_reject_unknown_values_without_touching_history(self):
        db = sqlite3.connect(':memory:')
        db.execute('CREATE TABLE campaign (id INTEGER PRIMARY KEY, status TEXT)')
        db.execute("""CREATE TRIGGER campaign_status_insert_guard BEFORE INSERT ON campaign
            WHEN NEW.status IS NULL OR NEW.status NOT IN
            ('legacy_active', 'draft', 'archived', 'closed')
            BEGIN SELECT RAISE(ABORT, 'Invalid campaign status'); END""")
        db.execute("""CREATE TRIGGER campaign_status_update_guard BEFORE UPDATE OF status ON campaign
            WHEN NEW.status IS NULL OR NEW.status NOT IN
            ('legacy_active', 'draft', 'archived', 'closed')
            BEGIN SELECT RAISE(ABORT, 'Invalid campaign status'); END""")
        db.execute("INSERT INTO campaign(status) VALUES ('archived')")
        for invalid in ('active', 'unexpected', None):
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute('INSERT INTO campaign(status) VALUES (?)', (invalid,))
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute('UPDATE campaign SET status=? WHERE id=1', (invalid,))
        self.assertEqual(db.execute('SELECT status FROM campaign').fetchone()[0], 'archived')
        db.close()


if __name__ == '__main__':
    unittest.main()
