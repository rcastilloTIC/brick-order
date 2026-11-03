"""Guard against invalid phase and zero-quantity vote mutations."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def _vote():
    tree = ast.parse((ROOT / "app/main/routes.py").read_text(encoding="utf-8"))
    return next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "submit_vote")

def test_vote_rejects_unsupported_phase_before_database_mutation():
    node = _vote()
    phase_guard = next(n for n in node.body if isinstance(n, ast.If) and isinstance(n.test, ast.Compare) and isinstance(n.test.left, ast.Name) and n.test.left.id == "phase")
    assert isinstance(phase_guard.test.ops[0], ast.NotIn)
    assert ast.literal_eval(phase_guard.test.comparators[0]) == {"first", "second", "order"}
    assert any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "abort" for n in ast.walk(phase_guard))

def test_vote_rejects_zero_and_negative_quantities():
    node = _vote()
    assert any(isinstance(n, ast.Compare) and any(isinstance(op, ast.LtE) for op in n.ops) and any(isinstance(c, ast.Constant) and c.value == 0 for c in n.comparators) for n in ast.walk(node))
    assert any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "assert_nondecreasing_vote" for n in ast.walk(node))

def test_vote_does_not_delete_existing_commitment():
    node = _vote()
    assert not any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "delete" for n in ast.walk(node))
