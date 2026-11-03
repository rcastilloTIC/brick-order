"""Exercise the real _ensure_schema() without importing Flask.

Extracting the function AST avoids mocks of its SQL and requires only SQLAlchemy.
This is an integration test of the application's actual SQLite DDL.
"""
import ast
import types
import unittest
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool


ROOT = Path(__file__).resolve().parents[1]


def schema_bootstrap(engine):
    source = (ROOT / "app" / "__init__.py").read_text(encoding="utf-8")
    module = ast.parse(source)
    fn = next(node for node in module.body if isinstance(node, ast.FunctionDef) and node.name == "_ensure_schema")
    namespace = {"db": types.SimpleNamespace(engine=engine)}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), str(ROOT / "app" / "__init__.py"), "exec"), namespace)
    namespace["_ensure_schema"]()


def database(include_favorites=True):
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE campaign (id INTEGER PRIMARY KEY, year INTEGER, status TEXT)"))
        conn.execute(text("CREATE TABLE product (id INTEGER PRIMARY KEY, campaign_id INTEGER)"))
        conn.execute(text("CREATE TABLE campaign_participation (id INTEGER PRIMARY KEY, campaign_id INTEGER, user_id INTEGER)"))
        for table in (("order", "user_vote", "user_favorite") if include_favorites else ("order", "user_vote")):
            conn.execute(text(f'CREATE TABLE "{table}" (id INTEGER PRIMARY KEY, campaign_id INTEGER, product_id INTEGER, user_id INTEGER, quantity INTEGER, phase TEXT)'))
        conn.execute(text("INSERT INTO campaign VALUES (1, 2026, 'legacy_active')"))
        conn.execute(text("INSERT INTO product (id, campaign_id) VALUES (10, 1)"))
        conn.execute(text("INSERT INTO campaign_participation VALUES (1, 1, 5)"))
    return engine


class ActualSchemaBootstrapTests(unittest.TestCase):
    def test_real_bootstrap_installs_guards_and_is_idempotent(self):
        for favorites in (True, False):
            with self.subTest(favorites=favorites):
                engine = database(favorites)
                schema_bootstrap(engine)
                schema_bootstrap(engine)
                with engine.begin() as conn:
                    conn.execute(text('INSERT INTO "order" (id,campaign_id,product_id,user_id) VALUES (1, 1, 10, 5)'))
                    with self.assertRaises(Exception):
                        conn.execute(text('INSERT INTO "order" (id,campaign_id,product_id,user_id) VALUES (2, 1, 10, 99)'))
                    with self.assertRaises(Exception):
                        conn.execute(text('UPDATE product SET campaign_id=2 WHERE id=10'))
                    with self.assertRaises(Exception):
                        conn.execute(text('DELETE FROM campaign_participation WHERE id=1'))
                    conn.execute(text("UPDATE campaign SET status='archived' WHERE id=1"))
                    conn.execute(text("INSERT INTO campaign VALUES (2, 2027, 'draft')"))
                    with self.assertRaises(Exception):
                        conn.execute(text("UPDATE campaign SET status='legacy_active' WHERE id=1"))
                    self.assertEqual(conn.execute(text('SELECT COUNT(*) FROM "order"')).scalar(), 1)
                engine.dispose()

    def test_real_bootstrap_rejects_existing_cross_campaign_records(self):
        engine = database()
        with engine.begin() as conn:
            conn.execute(text('INSERT INTO "order" (id,campaign_id,product_id,user_id) VALUES (1, 2, 10, 5)'))
        with self.assertRaisesRegex(RuntimeError, "Cross-campaign product links"):
            schema_bootstrap(engine)
        with engine.connect() as conn:
            self.assertEqual(conn.execute(text('SELECT campaign_id FROM "order" WHERE id=1')).scalar(), 2)
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
