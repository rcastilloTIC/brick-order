import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('archive_guard', ROOT / 'scripts/install_archive_guards.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class ArchiveSQLiteTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'db.sqlite'
        self.con = sqlite3.connect(self.path)
        self.addCleanup(self.con.close)
        self.con.executescript('''
        CREATE TABLE campaign(id INTEGER PRIMARY KEY, status TEXT);
        CREATE TABLE product(id INTEGER PRIMARY KEY, campaign_id INTEGER);
        CREATE TABLE "order"(id INTEGER PRIMARY KEY, campaign_id INTEGER);
        CREATE TABLE user_vote(id INTEGER PRIMARY KEY, campaign_id INTEGER);
        CREATE TABLE user_favorite(id INTEGER PRIMARY KEY, campaign_id INTEGER);
        CREATE TABLE campaign_participation(id INTEGER PRIMARY KEY, campaign_id INTEGER);
        INSERT INTO campaign VALUES(1,'archived'),(2,'legacy_active');
        ''')
        for table in mod.TABLES:
            self.con.execute(f'INSERT INTO "{table}" VALUES(1,1),(2,2)')
        self.con.commit()

    def test_dry_run(self):
        self.assertFalse(mod.install(self.path)['applied'])
        self.assertEqual(self.con.execute("SELECT count(*) FROM sqlite_master WHERE type='trigger'").fetchone()[0],0)

    def test_historical_rows_are_locked(self):
        self.assertEqual(mod.install(self.path,apply=True)['triggers'],17)
        for table in mod.TABLES:
            with self.subTest(table=table):
                for sql in (f'DELETE FROM "{table}" WHERE id=1',
                            f'UPDATE "{table}" SET campaign_id=2 WHERE id=1',
                            f'INSERT INTO "{table}" VALUES(99,1)',
                            f'UPDATE "{table}" SET campaign_id=1 WHERE id=2'):
                    with self.assertRaises(sqlite3.IntegrityError):
                        self.con.execute(sql)
                self.con.execute(f'UPDATE "{table}" SET campaign_id=2 WHERE id=2')
        with self.assertRaises(sqlite3.IntegrityError):
            self.con.execute("UPDATE campaign SET status='legacy_active' WHERE id=1")
        self.con.execute("UPDATE campaign SET status='archived' WHERE id=2")
        with self.assertRaises(sqlite3.IntegrityError):
            self.con.execute('DELETE FROM product WHERE id=2')

    def test_idempotent(self):
        mod.install(self.path,apply=True)
        mod.install(self.path,apply=True)
        self.assertEqual(self.con.execute("SELECT count(*) FROM sqlite_master WHERE type='trigger'").fetchone()[0],17)

    def test_incomplete_schema_rejected(self):
        self.con.execute('DROP TABLE campaign_participation')
        self.con.commit()
        with self.assertRaises(mod.ArchiveGuardError):
            mod.install(self.path,apply=True)
