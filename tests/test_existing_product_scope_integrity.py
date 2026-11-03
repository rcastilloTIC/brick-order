"""Exercise the exact existing-row integrity query used during schema initialization."""
import re
import sqlite3
from pathlib import Path

import pytest


SOURCE = (Path(__file__).resolve().parents[1] / 'app' / '__init__.py').read_text()


def existing_row_query(table):
    match = re.search(r'invalid = conn.execute\(text\(f"""(SELECT COUNT\(\*\) FROM \"\{table\}\" AS r.*?)"""\)\)\.scalar\(\)', SOURCE, re.S)
    assert match, 'Expected existing-row audit query not found in schema initialization'
    return match.group(1).replace('{table}', table)


@pytest.mark.parametrize('table', ['order', 'user_vote', 'user_favorite'])
def test_existing_row_audit_detects_missing_or_foreign_products(table):
    con = sqlite3.connect(':memory:')
    con.execute('CREATE TABLE product (id INTEGER PRIMARY KEY, campaign_id INTEGER)')
    con.execute(f'CREATE TABLE "{table}" (id INTEGER PRIMARY KEY, campaign_id INTEGER, product_id INTEGER)')
    con.executemany('INSERT INTO product VALUES (?, ?)', [(1, 2026), (2, 2027), (3, None)])
    con.executemany(f'INSERT INTO "{table}" VALUES (?, ?, ?)', [
        (1, 2026, 1), (2, 2026, 2), (3, 2026, 3), (4, 2026, 999),
        (5, None, 2),
    ])
    assert con.execute(existing_row_query(table)).fetchone()[0] == 3
    con.execute(f'DELETE FROM "{table}" WHERE id IN (2, 3, 4)')
    assert con.execute(existing_row_query(table)).fetchone()[0] == 0
    con.close()
