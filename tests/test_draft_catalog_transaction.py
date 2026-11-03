"""Exercise the real draft import service with a transactional SQLite adapter."""
import ast
import math
import sqlite3
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'app/services/draft_catalog_import.py'

class Query:
    session_global = None
    def __init__(self, conn, model, filters=None):
        self.conn, self.model, self.filters = conn, model, filters or {}
        self.session = Query.session_global
    def filter_by(self, **kwargs):
        return Query(self.conn, self.model, {**self.filters, **kwargs})
    def all(self):
        where = ' AND '.join(f'{k}=?' for k in self.filters) or '1=1'
        table = 'campaign' if self.model == 'campaign' else 'product'
        rows = self.conn.execute(f'SELECT * FROM {table} WHERE {where}', tuple(self.filters.values())).fetchall()
        if table == 'campaign':
            return [types.SimpleNamespace(id=r[0], year=r[1], status=r[2]) for r in rows]
        return [self.conn_identity(r) for r in rows]
    def conn_identity(self, r):
        obj = Product(id=r[0], campaign_id=r[1], reference=r[2], name=r[3], price=r[4], present_in_2025=bool(r[5]))
        self.session.tracked.append(obj)
        return obj
    def first(self):
        return next(iter(self.all()), None)
    def one_or_none(self):
        rows = self.all()
        if len(rows) > 1:
            raise ValueError('multiple rows')
        return rows[0] if rows else None

class Product:
    query = None
    def __init__(self, **kwargs):
        self.id = kwargs.pop('id', None)
        self.campaign_id = kwargs.pop('campaign_id')
        self.reference = kwargs.pop('reference')
        self.name = kwargs.pop('name', None)
        self.price = kwargs.pop('price', None)
        self.present_in_2025 = kwargs.pop('present_in_2025', True)
        for k, v in kwargs.items(): setattr(self, k, v)

class ActionLog:
    def __init__(self, **kwargs): self.__dict__.update(kwargs)

class Session:
    def __init__(self, conn): self.conn, self.pending, self.tracked = conn, [], []
    def add(self, obj): self.pending.append(obj)
    def commit(self):
        for obj in self.pending:
            if isinstance(obj, ActionLog):
                self.conn.execute('INSERT INTO action_log (user_id, action, detail) VALUES (?, ?, ?)', (obj.user_id, obj.action, obj.detail))
            elif obj.id is None:
                self.conn.execute('INSERT INTO product (campaign_id, reference, name, price, present_in_2025) VALUES (?, ?, ?, ?, ?)', (obj.campaign_id, obj.reference, obj.name, obj.price, int(obj.present_in_2025)))
            else:
                self.conn.execute('UPDATE product SET name=?, price=?, present_in_2025=? WHERE id=?', (obj.name, obj.price, int(obj.present_in_2025), obj.id))
        for obj in self.tracked:
            self.conn.execute('UPDATE product SET name=?, price=?, present_in_2025=? WHERE id=?', (obj.name, obj.price, int(obj.present_in_2025), obj.id))
        self.conn.commit()
        self.pending.clear()
        self.tracked.clear()
    def rollback(self): self.conn.rollback(); self.pending.clear(); self.tracked.clear()

def load_service(db, campaign, product):
    tree = ast.parse(SOURCE.read_text(encoding='utf-8'))
    nodes = [n for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'ALLOWED_CATALOG_FIELDS' for t in n.targets)]
    nodes += [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ('validate_draft_catalog_rows', 'import_draft_catalog')]
    ns = {'isfinite': math.isfinite, 'db': db, 'Campaign': campaign, 'Product': product, 'ActionLog': ActionLog}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), 'exec'), ns)
    return ns['import_draft_catalog']

class DraftCatalogTransactionTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(':memory:')
        self.conn.executescript("""CREATE TABLE campaign(id INTEGER PRIMARY KEY, year INTEGER, status TEXT);
CREATE TABLE product(id INTEGER PRIMARY KEY, campaign_id INTEGER, reference TEXT, name TEXT, price REAL, present_in_2025 INTEGER);
CREATE TABLE action_log(id INTEGER PRIMARY KEY, user_id INTEGER, action TEXT, detail TEXT);""")
        self.conn.executemany('INSERT INTO campaign VALUES (?, ?, ?)', [(1, 2026, 'archived'), (2, 2027, 'draft')])
        self.conn.executemany('INSERT INTO product(campaign_id,reference,name,price,present_in_2025) VALUES (?,?,?,?,?)', [(1,'A','Historico',9,1),(2,'B','Antiguo',2,1)])
        self.conn.commit()
        self.session = Session(self.conn)
        Query.session_global = self.session
        self.import_catalog = load_service(types.SimpleNamespace(session=self.session), types.SimpleNamespace(query=Query(self.conn, 'campaign')), Product)
        Product.query = Query(self.conn, 'product')
    def tearDown(self): self.conn.close()
    def products(self): return self.conn.execute('SELECT campaign_id,reference,name,price,present_in_2025 FROM product ORDER BY campaign_id,reference').fetchall()
    def test_import_upsert_and_archived_isolation(self):
        result = self.import_catalog(2, {'A': {'name': 'Nuevo', 'price': 1}}, actor_id=7)
        self.assertEqual(result, {'created': 1, 'updated': 0, 'missing': 1})
        self.assertEqual(self.products(), [(1,'A','Historico',9.0,1),(2,'A','Nuevo',1.0,1),(2,'B','Antiguo',2.0,0)])
        result = self.import_catalog(2, {'A': {'name': 'Actualizado', 'price': 3}}, actor_id=7)
        self.assertEqual(result, {'created': 0, 'updated': 1, 'missing': 1})
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM product WHERE campaign_id=2').fetchone()[0], 2)
    def test_invalid_rows_do_not_change_database(self):
        before = self.products()
        with self.assertRaises(ValueError): self.import_catalog(2, {'A': {'name': 'OK'}, 'a': {'name': 'Duplicado'}}, actor_id=7)
        self.assertEqual(self.products(), before)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM action_log').fetchone()[0], 0)
    def test_active_campaign_blocks_import(self):
        self.conn.execute("UPDATE campaign SET status='legacy_active' WHERE id=1")
        self.conn.commit()
        with self.assertRaises(ValueError): self.import_catalog(2, {'A': {'name': 'OK'}}, actor_id=7)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM action_log').fetchone()[0], 0)
    def test_archived_target_blocks_import(self):
        with self.assertRaises(ValueError): self.import_catalog(1, {'A': {'name': 'Cambio'}}, actor_id=7)
        self.assertEqual(self.products()[0][2], 'Historico')
    def test_audit_failure_rolls_back(self):
        self.conn.execute('CREATE TRIGGER reject_audit BEFORE INSERT ON action_log BEGIN SELECT RAISE(ABORT, "audit failed"); END;')
        before = self.products()
        with self.assertRaises(sqlite3.IntegrityError): self.import_catalog(2, {'A': {'name': 'Nuevo'}}, actor_id=7)
        self.assertEqual(self.products(), before)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM action_log').fetchone()[0], 0)

if __name__ == '__main__': unittest.main()
