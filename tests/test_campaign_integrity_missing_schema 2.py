"""Missing campaign tables fail closed without crashes or data mutation."""
import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'audit_campaign_integrity.py'
spec = importlib.util.spec_from_file_location('campaign_integrity_missing_schema', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class MissingSchemaTest(unittest.TestCase):
    def test_missing_campaign_table_with_scoped_product(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder) / 'legacy.sqlite'
            with sqlite3.connect(db) as con:
                con.execute('CREATE TABLE product (id INTEGER PRIMARY KEY, campaign_id INTEGER, price REAL)')
                con.execute('INSERT INTO product VALUES (1, 2026, 0.15)')
            before = db.read_bytes()
            report = module.audit_database(db)
            self.assertFalse(report['ok'])
            self.assertTrue(any('Missing tables:' in issue for issue in report['issues']))
            self.assertTrue(any('campaign ownership cannot be verified' in issue for issue in report['issues']))
            self.assertEqual(db.read_bytes(), before)

    def test_empty_sqlite_schema_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder) / 'empty.sqlite'
            sqlite3.connect(db).close()
            self.assertFalse(module.audit_database(db)['ok'])


if __name__ == '__main__':
    unittest.main()
