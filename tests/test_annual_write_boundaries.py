import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path

script = Path(__file__).resolve().parents[1] / 'scripts/install_annual_write_boundaries.py'
spec = importlib.util.spec_from_file_location('annual_boundary', script)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class BoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'test.db'
        with sqlite3.connect(self.path) as con:
            con.executescript('''
                CREATE TABLE campaign(id INTEGER PRIMARY KEY);
                CREATE TABLE product(id INTEGER PRIMARY KEY,campaign_id INTEGER);
                CREATE TABLE campaign_participation(id INTEGER PRIMARY KEY,campaign_id INTEGER,user_id INTEGER);
                CREATE TABLE "order"(id INTEGER PRIMARY KEY,campaign_id INTEGER,product_id INTEGER,user_id INTEGER);
                CREATE TABLE user_vote(id INTEGER PRIMARY KEY,campaign_id INTEGER,product_id INTEGER,user_id INTEGER);
                CREATE TABLE user_favorite(id INTEGER PRIMARY KEY,campaign_id INTEGER,product_id INTEGER,user_id INTEGER);
                INSERT INTO campaign VALUES(1),(2);
                INSERT INTO product VALUES(10,1),(20,2);
                INSERT INTO campaign_participation VALUES(1,1,7),(2,2,7);
            ''')

    def test_preflight_readonly(self):
        self.assertFalse(mod.install(self.path)['applied'])
        with sqlite3.connect(self.path) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='trigger'").fetchone()[0], 0)

    def test_all_three_tables_deny_year_or_member_mixing(self):
        self.assertEqual(mod.install(self.path, apply=True)['triggers'], 9)
        with sqlite3.connect(self.path) as con:
            for table in mod.TABLES:
                con.execute(f'INSERT INTO "{table}"(campaign_id,product_id,user_id) VALUES(1,10,7)')
                for product, user in ((20,7),(10,99)):
                    with self.assertRaises(sqlite3.IntegrityError):
                        con.execute(f'INSERT INTO "{table}"(campaign_id,product_id,user_id) VALUES(1,?,?)', (product,user))
                with self.assertRaises(sqlite3.IntegrityError):
                    con.execute(f'UPDATE "{table}" SET campaign_id=2 WHERE campaign_id=1')

    def test_existing_bad_rows_rejected(self):
        with sqlite3.connect(self.path) as con:
            con.execute('INSERT INTO "order"(campaign_id,product_id,user_id) VALUES(1,20,7)')
        with self.assertRaises(mod.BoundaryError):
            mod.install(self.path, apply=True)

    def test_cannot_move_product_or_membership(self):
        mod.install(self.path, apply=True)
        with sqlite3.connect(self.path) as con:
            con.execute('INSERT INTO "order"(campaign_id,product_id,user_id) VALUES(1,10,7)')
            for sql in ('UPDATE product SET campaign_id=2 WHERE id=10',
                        'DELETE FROM campaign_participation WHERE id=1',
                        'UPDATE campaign_participation SET campaign_id=2 WHERE id=1'):
                with self.assertRaises(sqlite3.IntegrityError):
                    con.execute(sql)

    def test_idempotent(self):
        mod.install(self.path, apply=True)
        self.assertEqual(mod.install(self.path, apply=True)['triggers'], 9)
        with sqlite3.connect(self.path) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='trigger'").fetchone()[0], 9)


if __name__ == '__main__':
    unittest.main()
