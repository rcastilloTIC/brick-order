"""Regression tests for fail-closed lifecycle integrity audit."""
import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "audit_campaign_integrity.py"
spec = importlib.util.spec_from_file_location("audit_campaign_lifecycle", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class CampaignLifecycleAuditTests(unittest.TestCase):
    def _audit(self, schema, rows=()):
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder) / "history.sqlite"
            with sqlite3.connect(db) as conn:
                conn.execute(schema)
                for query in rows:
                    conn.execute(query)
            before = db.read_bytes()
            result = module.audit_database(db)
            self.assertEqual(before, db.read_bytes(), "Audit mutated database")
            return result

    def test_single_campaign_without_status_rejected(self):
        report = self._audit("CREATE TABLE campaign (id INTEGER PRIMARY KEY)",
                             ("INSERT INTO campaign VALUES (2026)",))
        self.assertFalse(report["ok"])
        self.assertTrue(any("status column missing" in issue for issue in report["issues"]))

    def test_unknown_status_rejected(self):
        report = self._audit("CREATE TABLE campaign (id INTEGER PRIMARY KEY, status TEXT)",
                             ("INSERT INTO campaign VALUES (2026, 'unknown')",))
        self.assertFalse(report["ok"])
        self.assertTrue(any("lifecycle statuses" in issue for issue in report["issues"]))

    def test_null_status_rejected(self):
        report = self._audit("CREATE TABLE campaign (id INTEGER PRIMARY KEY, status TEXT)",
                             ("INSERT INTO campaign VALUES (2026, NULL)",))
        self.assertFalse(report["ok"])
        self.assertTrue(any("lifecycle statuses" in issue for issue in report["issues"]))

if __name__ == "__main__":
    unittest.main()
