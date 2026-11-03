"""SQLite migration safety tests; no Flask dependency required."""
import importlib.util
from pathlib import Path
import sqlite3
import tempfile
import unittest

MIGRATION_PATH = Path(__file__).resolve().parents[1] / 'scripts' / 'prepare_campaign_columns.py'
spec = importlib.util.spec_from_file_location('prepare_campaign_columns', MIGRATION_PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class AnnualMigrationTests(unittest.TestCase):
   def setUp(self):
       self.temp = tempfile.TemporaryDirectory()
       self.addCleanup(self.temp.cleanup)
       self.path = Path(self.temp.name) / 'campaign.db'
       with sqlite3.connect(self.path) as conn:
           conn.execute('CREATE TABLE campaign (id INTEGER PRIMARY KEY, year INTEGER)')
           conn.execute('INSERT INTO campaign VALUES (1, 2026)')
           for table in module.TABLES:
               conn.execute(f'CREATE TABLE "{table}" (id INTEGER PRIMARY KEY)')
               conn.execute(f'INSERT INTO "{table}" VALUES (7)')

   def test_dry_run_does_not_modify(self):
       result = module.prepare(self.path)
       self.assertFalse(result['applied'])
       with sqlite3.connect(self.path) as conn:
           self.assertNotIn('campaign_id', [c[1] for c in conn.execute('PRAGMA table_info(product)')])

   def test_apply_is_idempotent_and_backed_up(self):
       first = module.prepare(self.path, apply=True)
       self.assertTrue(Path(first['backup']).is_file())
       second = module.prepare(self.path, apply=True)
       self.assertEqual(second['new_columns'], [])
       with sqlite3.connect(self.path) as conn:
           for table in module.TABLES:
               self.assertEqual(conn.execute(f'SELECT campaign_id FROM "{table}"').fetchone()[0], 1)

   def test_multiple_campaigns_are_refused_without_changes(self):
       with sqlite3.connect(self.path) as conn:
           conn.execute('INSERT INTO campaign VALUES (2, 2027)')
       with self.assertRaises(module.MigrationError):
           module.prepare(self.path, apply=True)
       self.assertEqual(list(self.path.parent.glob('*.bak')), [])

   def test_wrong_campaign_assignment_is_refused(self):
       with sqlite3.connect(self.path) as conn:
           conn.execute('ALTER TABLE product ADD COLUMN campaign_id INTEGER')
           conn.execute('UPDATE product SET campaign_id=9')
       with self.assertRaises(module.MigrationError):
           module.prepare(self.path, apply=True)


if __name__ == '__main__':
   unittest.main()
