"""Regression for optional tables in SQLite product-campaign guards."""
import sqlite3
import unittest
from pathlib import Path


class OptionalProductLinkTables(unittest.TestCase):
    def test_reverse_guard_works_without_favorites_table(self):
        db = sqlite3.connect(":memory:")
        db.executescript("""
            CREATE TABLE product(id INTEGER PRIMARY KEY, campaign_id INTEGER);
            CREATE TABLE "order"(id INTEGER PRIMARY KEY, product_id INTEGER, campaign_id INTEGER);
            CREATE TABLE user_vote(id INTEGER PRIMARY KEY, product_id INTEGER, campaign_id INTEGER);
            INSERT INTO product VALUES(1, 2026), (2, 2026);
            INSERT INTO "order" VALUES(1, 1, 2026);
        """)
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        linked = [table for table in ('order', 'user_vote', 'user_favorite') if table in tables]
        refs = ' OR '.join(
            f'EXISTS (SELECT 1 FROM "{table}" r WHERE r.product_id = OLD.id '
            'AND r.campaign_id IS NOT NULL AND '
            '(NEW.campaign_id IS NULL OR r.campaign_id != NEW.campaign_id))'
            for table in linked
        )
        db.execute(f"""CREATE TRIGGER bom_product_campaign_move_guard
            BEFORE UPDATE OF campaign_id ON product WHEN {refs}
            BEGIN SELECT RAISE(ABORT, 'Product campaign has linked records'); END""")
        db.execute('UPDATE product SET campaign_id=2027 WHERE id=2')
        with self.assertRaises(sqlite3.IntegrityError):
            db.execute('UPDATE product SET campaign_id=2027 WHERE id=1')
        self.assertEqual(db.execute('SELECT campaign_id FROM product WHERE id=1').fetchone()[0], 2026)
        db.close()

    def test_application_constructs_guard_from_existing_tables(self):
        source = (Path(__file__).resolve().parents[1] / 'app' / '__init__.py').read_text()
        self.assertIn('linked_product_tables = []', source)
        self.assertIn('if linked_table not in tables:', source)
        self.assertIn('for linked_table in linked_product_tables', source)
        self.assertIn('BEFORE {operation} ON "{table}"', source)


if __name__ == '__main__':
    unittest.main()
