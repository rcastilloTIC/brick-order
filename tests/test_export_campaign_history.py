"""SQLite integration checks for historical campaign CSV export."""
import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / 'scripts' / 'export_campaign_history.py'
spec = importlib.util.spec_from_file_location('campaign_history_export', PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class HistoryExportTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / 'test.db'
        self.out = Path(self.tmp.name) / 'history'
        with sqlite3.connect(self.db) as con:
            con.executescript('''
                CREATE TABLE campaign (id INTEGER, year INTEGER, title TEXT, status TEXT);
                CREATE TABLE campaign_participation (id INTEGER, campaign_id INTEGER, user_id INTEGER, status TEXT);
                CREATE TABLE product (id INTEGER, campaign_id INTEGER, reference TEXT, name TEXT, price REAL, final_selected INTEGER);
                CREATE TABLE user_vote (id INTEGER, campaign_id INTEGER, user_id INTEGER, product_id INTEGER, quantity INTEGER);
                CREATE TABLE user_favorite (id INTEGER, campaign_id INTEGER, user_id INTEGER, product_id INTEGER);
                CREATE TABLE "order" (id INTEGER, campaign_id INTEGER, user_id INTEGER, product_id INTEGER, quantity INTEGER);
                INSERT INTO campaign VALUES (1, 2025, '2025', 'archived'), (2, 2026, '2026', 'legacy_active');
                INSERT INTO product VALUES (10, 1, 'AAA', 'Old', 1.5, 1), (20, 2, 'BBB', 'New', 2, 1);
                INSERT INTO user_vote VALUES (1, 1, 7, 10, 50), (2, 2, 7, 20, 60);
                INSERT INTO "order" VALUES (1, 1, 7, 10, 50), (2, 2, 7, 20, 60);
            ''')

    def test_archive_is_isolated_and_consistent(self):
        manifest = module.export_campaign(self.db, 1, self.out)
        self.assertEqual(manifest['campaign']['year'], 2025)
        self.assertEqual(manifest['files']['votes.csv']['rows'], 1)
        content = (self.out / 'votes.csv').read_text(encoding='utf-8-sig')
        self.assertIn('10,50', content)
        self.assertNotIn('20,60', content)
        self.assertFalse(any('password' in x.name for x in self.out.iterdir()))

    def test_active_campaign_rejected(self):
        with self.assertRaises(ValueError):
            module.export_campaign(self.db, 2, self.out)
        self.assertFalse(self.out.exists())

    def test_cross_campaign_reference_rejected(self):
        with sqlite3.connect(self.db) as con:
            con.execute('UPDATE user_vote SET product_id=20 WHERE id=1')
        with self.assertRaises(ValueError):
            module.export_campaign(self.db, 1, self.out)
        self.assertFalse(self.out.exists())

    def test_never_overwrites_existing_export(self):
        module.export_campaign(self.db, 1, self.out)
        with self.assertRaises(FileExistsError):
            module.export_campaign(self.db, 1, self.out)


if __name__ == '__main__':
    unittest.main()
