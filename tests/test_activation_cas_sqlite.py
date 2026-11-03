"""Execute the actual activation compare-and-swap SQL against SQLite."""
import ast
import unittest
from pathlib import Path
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]


def promotion_sql():
    tree = ast.parse((ROOT / 'app/services/campaign_activation.py').read_text())
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
              and n.name == 'activate_prepared_draft')
    statements = [n.args[0].value for n in ast.walk(fn)
                  if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                  and n.func.id == 'text' and n.args
                  and isinstance(n.args[0], ast.Constant)
                  and isinstance(n.args[0].value, str)]
    return next(sql for sql in statements if 'UPDATE campaign' in sql)


class ActivationCASTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        with self.engine.begin() as c:
            c.execute(text('CREATE TABLE campaign (id INTEGER PRIMARY KEY, year INTEGER, status TEXT)'))
            c.execute(text("INSERT INTO campaign VALUES (1, 2026, 'archived'), (2, 2027, 'draft')"))

    def tearDown(self):
        self.engine.dispose()

    def promote(self):
        with self.engine.begin() as c:
            result = c.execute(text(promotion_sql()), {'campaign_id': 2})
            return result.rowcount

    def test_valid_draft_activates_once_only(self):
        self.assertEqual(self.promote(), 1)
        self.assertEqual(self.promote(), 0)
        with self.engine.connect() as c:
            self.assertEqual(c.execute(text('SELECT status FROM campaign WHERE id=1')).scalar(), 'archived')

    def test_draft_archived_while_preflight_was_running(self):
        with self.engine.begin() as c:
            c.execute(text("UPDATE campaign SET status='archived' WHERE id=2"))
        self.assertEqual(self.promote(), 0)

    def test_new_active_campaign_prevents_promotion(self):
        with self.engine.begin() as c:
            c.execute(text("INSERT INTO campaign VALUES (3, 2028, 'legacy_active')"))
        self.assertEqual(self.promote(), 0)

    def test_second_draft_prevents_promotion(self):
        with self.engine.begin() as c:
            c.execute(text("INSERT INTO campaign VALUES (3, 2028, 'draft')"))
        self.assertEqual(self.promote(), 0)


if __name__ == '__main__':
    unittest.main()
