"""SQLite transaction tests using the actual pure commitment planner."""
import ast
import sqlite3
from collections import defaultdict
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
tree = ast.parse((ROOT / 'app/services/order_materialization.py').read_text())
node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'missing_order_floors')
ns = {'defaultdict': defaultdict}
exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])), '<planner>', 'exec'), ns)
planner = ns['missing_order_floors']

@pytest.mark.parametrize('failure', ['selection', 'orders', 'phase', None])
def test_sqlite_atomicity_and_campaign_isolation(tmp_path, failure):
    db = sqlite3.connect(tmp_path / 'test.db', isolation_level=None)
    db.executescript("""
    CREATE TABLE products (campaign INT, id INT, selected INT);
    CREATE TABLE votes (campaign INT, user INT, product INT, quantity INT);
    CREATE TABLE orders (campaign INT, user INT, product INT, quantity INT);
    CREATE TABLE phases (campaign INT PRIMARY KEY, phase TEXT);
    INSERT INTO products VALUES (1,10,0),(1,11,0),(2,10,0);
    INSERT INTO votes VALUES (1,5,10,3),(1,5,11,7),(2,5,10,8);
    INSERT INTO orders VALUES (1,5,10,1);
    INSERT INTO phases VALUES (1,'final'),(2,'final');
    """)
    try:
        db.execute('BEGIN')
        db.execute('UPDATE products SET selected=1 WHERE campaign=1 AND id=10')
        if failure == 'selection': raise RuntimeError('injected')
        selected = {r[0] for r in db.execute('SELECT id FROM products WHERE campaign=1 AND selected=1')}
        votes = list(db.execute('SELECT user, product, quantity FROM votes WHERE campaign=1'))
        orders = list(db.execute('SELECT user, product, quantity FROM orders WHERE campaign=1'))
        for (user, product), quantity in planner(votes, orders, selected).items():
            db.execute('INSERT INTO orders VALUES (1,?,?,?)', (user, product, quantity))
        if failure == 'orders': raise RuntimeError('injected')
        db.execute("UPDATE phases SET phase='order' WHERE campaign=1")
        if failure == 'phase': raise RuntimeError('injected')
        db.commit()
    except RuntimeError:
        db.rollback()
    assert db.execute('SELECT phase FROM phases WHERE campaign=1').fetchone()[0] == ('order' if failure is None else 'final')
    assert db.execute('SELECT phase FROM phases WHERE campaign=2').fetchone()[0] == 'final'
    assert db.execute('SELECT selected FROM products WHERE campaign=2').fetchone()[0] == 0
    assert db.execute('SELECT quantity FROM votes WHERE campaign=1 AND product=11').fetchone()[0] == 7
    assert db.execute('SELECT SUM(quantity) FROM orders WHERE campaign=1 AND product=10').fetchone()[0] == (3 if failure is None else 1)
    assert db.execute('SELECT selected FROM products WHERE campaign=1 AND id=10').fetchone()[0] == (1 if failure is None else 0)
    db.close()

def test_verification_precedes_phase_update():
    tree = ast.parse((ROOT / 'app/main/routes.py').read_text())
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'advance_order_phase')
    code = ast.unparse(fn)
    assert code.index('materialize_selected_commitments()') < code.index('assert_selected_commitments_materialized()') < code.index("set_current_phase('order', commit=False)")
