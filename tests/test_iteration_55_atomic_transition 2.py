"""Regression checks for the single-commit final-to-order boundary."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def function(path, name):
    tree = ast.parse((ROOT / path).read_text())
    return next(node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name)

def test_transition_has_single_commit_and_rollback():
    node = function('app/main/routes.py', 'advance_order_phase')
    src = ast.unparse(node)
    assert src.count('db.session.commit()') == 1
    assert 'db.session.rollback()' in src
    assert "compute_final_selection(limit=limits['final_selection_limit'], commit=False)" in src
    assert "set_current_phase('order', commit=False)" in src
    assert src.index('materialize_selected_commitments()') < src.index("set_current_phase('order', commit=False)") < src.index('db.session.commit()')

def test_services_support_deferred_commit():
    for path, name in [('app/models.py','set'),('app/services/campaign_phase.py','set_campaign_phase'),('app/services/final_selection.py','_persist_final_selection'),('app/services/final_selection.py','compute_final_selection'),('app/main/routes.py','set_current_phase')]:
        node = function(path,name)
        assert 'commit' in [a.arg for a in node.args.kwonlyargs], (path,name)
    assert 'if commit:' in (ROOT/'app/services/final_selection.py').read_text()
