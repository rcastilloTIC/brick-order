"""Regression checks against the real pure transfer planner."""
import ast
from collections import defaultdict
from pathlib import Path
import pytest

source = Path(__file__).resolve().parents[1] / "app/services/order_materialization.py"
tree = ast.parse(source.read_text(encoding="utf-8"))
planner = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "missing_order_floors")
namespace = {"defaultdict": defaultdict}
exec(compile(ast.Module(body=[planner], type_ignores=[]), str(source), "exec"), namespace)
plan = namespace["missing_order_floors"]


def test_cutoff_and_no_duplicate_transfer():
    votes = [(7, product, 3) for product in range(1, 87)]
    selected = set(range(1, 86))
    existing = [(7, 1, 2), (7, 2, 4)]
    missing = plan(votes, existing, selected)
    assert len(missing) == 84
    assert missing[(7, 1)] == 1
    assert (7, 2) not in missing
    assert (7, 86) not in missing
    transferred = existing + [(u, p, q) for (u, p), q in missing.items()]
    assert plan(votes, transferred, selected) == {}
    assert votes[-1] == (7, 86, 3)


def test_different_participants_are_independent():
    assert plan([(1, 3, 5), (2, 3, 8)], [(1, 3, 5)], {3}) == {(2, 3): 8}


@pytest.mark.parametrize("selected", [None, [0], [-1], [True], [1, "2"]])
def test_invalid_selection_rejected(selected):
    with pytest.raises(ValueError):
        plan([], [], selected)


@pytest.mark.parametrize("votes, orders", [
    ([(0, 1, 3)], []), ([(True, 1, 3)], []),
    ([(1, -1, 3)], []), ([], [(0, 1, 3)]),
    ([], [(1, True, 3)]),
])
def test_invalid_identity_rejected(votes, orders):
    with pytest.raises(ValueError):
        plan(votes, orders, {1})


def test_empty_selection_does_not_transfer():
    assert plan([(1, 1, 4)], [], set()) == {}


def test_materialization_requires_confirmed_selection():
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "materialize_selected_commitments")
    assert any(isinstance(node, ast.If) and isinstance(node.test, ast.UnaryOp)
               and isinstance(node.test.op, ast.Not) and isinstance(node.test.operand, ast.Name)
               and node.test.operand.id == "selected" for node in ast.walk(function))
