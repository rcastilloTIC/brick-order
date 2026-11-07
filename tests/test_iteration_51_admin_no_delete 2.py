"""Regression: administrative mutations cannot delete votes."""
import ast
from pathlib import Path

ROUTES = Path(__file__).resolve().parents[1] / "app/main/routes.py"


def _admin_function(name):
    tree = ast.parse(ROUTES.read_text(encoding="utf-8"))
    return next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name)


def test_no_delete_or_zero_branch_in_admin_mutations():
    for name in ("admin_update_order", "admin_add_order"):
        node = _admin_function(name)
        assert not any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "delete" for n in ast.walk(node))
        assert not any(isinstance(n, ast.Constant) and n.value == "admin_order_delete" for n in ast.walk(node))
        assert not any(isinstance(n, ast.Compare) and isinstance(n.left, ast.Name) and n.left.id == "quantity" and any(isinstance(c, ast.Constant) and c.value == 0 for c in n.comparators) and any(isinstance(op, ast.Eq) for op in n.ops) for n in ast.walk(node))


def test_validation_and_commitment_guards_preserved():
    for name in ("admin_update_order", "admin_add_order"):
        node = _admin_function(name)
        calls = {n.func.id for n in ast.walk(node) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        assert {"assert_nondecreasing_vote", "require_campaign_participant", "_validate_quantity_for_product"} <= calls
        assert any(isinstance(n, ast.Compare) and any(isinstance(op, ast.LtE) for op in n.ops) and any(isinstance(c, ast.Constant) and c.value == 0 for c in n.comparators) for n in ast.walk(node))
