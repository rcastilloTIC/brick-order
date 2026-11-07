"""Ensure rejected phase transitions do not persist selection or run backups."""
import ast
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "app/main/routes.py"
TREE = ast.parse(SOURCE.read_text(encoding="utf-8"))


def test_order_transition_preflight_is_read_only_and_precedes_backup():
    route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef)
                 and node.name == "advance_order_phase")
    calls = [node for node in ast.walk(route) if isinstance(node, ast.Call)]
    selection_calls = sorted((node for node in calls if isinstance(node.func, ast.Name)
                              and node.func.id == "compute_final_selection"), key=lambda n: n.lineno)
    backups = [node for node in calls if isinstance(node.func, ast.Name)
               and node.func.id == "_attempt_phase_backup"]
    assert len(selection_calls) == 2
    assert len(backups) == 1
    assert selection_calls[0].lineno < backups[0].lineno < selection_calls[1].lineno
    assert any(keyword.arg == "persist" and isinstance(keyword.value, ast.Constant)
               and keyword.value.value is False for keyword in selection_calls[0].keywords)
    assert not any(keyword.arg == "persist" for keyword in selection_calls[1].keywords)


def test_rejected_selection_includes_empty_result():
    route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef)
                 and node.name == "advance_order_phase")
    guard = next(node for node in ast.walk(route) if isinstance(node, ast.If)
                 and isinstance(node.test, ast.BoolOp)
                 and any(isinstance(part, ast.UnaryOp) and isinstance(part.operand, ast.Subscript)
                         and isinstance(part.operand.value, ast.Name)
                         and part.operand.value.id == "summary"
                         for part in node.test.values))
    assert "selected_count" in ast.unparse(guard.test)
