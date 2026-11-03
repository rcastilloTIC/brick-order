"""Regression checks for administrative vote quantity validation."""
import ast
from pathlib import Path

ROUTES = Path(__file__).resolve().parents[1] / "app/main/routes.py"

def _function(name):
    tree = ast.parse(ROUTES.read_text(encoding="utf-8"))
    return next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == name)

def test_admin_mutations_reject_zero_before_loading_vote():
    for name in ("admin_update_order", "admin_add_order"):
        node = _function(name)
        checks = [n for n in ast.walk(node) if isinstance(n, ast.Compare) and any(isinstance(op, ast.LtE) for op in n.ops) and any(isinstance(c, ast.Constant) and c.value == 0 for c in n.comparators)]
        assert checks, name
        assert any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "assert_nondecreasing_vote" for n in ast.walk(node)), name

def test_admin_mutations_require_campaign_participation():
    for name in ("admin_update_order", "admin_add_order"):
        assert any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "require_campaign_participant" for n in ast.walk(_function(name)))
