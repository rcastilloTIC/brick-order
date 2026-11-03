"""SQLite schema contract without requiring Flask dependencies.

These tests inspect the actual SQLAlchemy model declarations and exercise SQLite
schema creation/reopening; they do not claim to test Flask's db.create_all().
"""
import ast
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _declared_tables(root):
    tree = ast.parse((root / 'app/models.py').read_text(encoding='utf-8'))
    return {node.value.value for cls in tree.body if isinstance(cls, ast.ClassDef)
            for node in cls.body if isinstance(node, ast.Assign)
            for target in node.targets if isinstance(target, ast.Name)
            and target.id == '__tablename__' and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)}


def test_public_model_table_names_are_unique():
    tree = ast.parse((ROOT / 'app/models.py').read_text(encoding='utf-8'))
    names = [node.value.value for cls in tree.body if isinstance(cls, ast.ClassDef)
             for node in cls.body if isinstance(node, ast.Assign)
             for target in node.targets if isinstance(target, ast.Name)
             and target.id == '__tablename__' and isinstance(node.value, ast.Constant)]
    assert names and len(names) == len(set(names))


def test_sqlite_reopen_preserves_existing_records(tmp_path):
    path = tmp_path / 'campaign.sqlite'
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE campaign (id INTEGER PRIMARY KEY, year INTEGER NOT NULL)')
        conn.execute('INSERT INTO campaign (year) VALUES (2026)')
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS campaign (id INTEGER PRIMARY KEY, year INTEGER NOT NULL)')
        assert conn.execute('SELECT year FROM campaign').fetchall() == [(2026,)]


def test_extended_retains_additional_model_tables():
    extended = ROOT.parent / 'extended'
    if not (extended / 'app/models.py').exists():
        import pytest
        pytest.skip('Extended checkout not available alongside public checkout')
    assert _declared_tables(ROOT) < _declared_tables(extended)
