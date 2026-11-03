"""Offline checks: make sure the ORM scenarios are included in the deliverable."""
import ast
from pathlib import Path


def test_complete_transition_scenarios_exist():
    path = Path(__file__).with_name("test_iteration_58_flask_sqlalchemy_integration.py")
    tree = ast.parse(path.read_text())
    names = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
    assert {"test_full_selection_order_phase_transaction_rolls_back",
            "test_full_selection_order_phase_transaction_commits"} <= names


def test_rollback_scenario_exercises_real_services():
    path = Path(__file__).with_name("test_iteration_58_flask_sqlalchemy_integration.py")
    tree = ast.parse(path.read_text())
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                    and node.name == "test_full_selection_order_phase_transaction_rolls_back")
    calls = {node.func.id for node in ast.walk(function)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    assert {"compute_final_selection", "materialize_selected_commitments",
            "assert_selected_commitments_materialized", "set_campaign_phase"} <= calls
    assert 'db.session.rollback()' in ast.get_source_segment(path.read_text(), function)
