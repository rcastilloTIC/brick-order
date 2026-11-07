"""Dependency-free regression checks for the optional integration suite."""
import ast
from pathlib import Path


def test_integration_suite_uses_existing_phase_api():
    root = Path(__file__).resolve().parents[1]
    integration = (root / "tests/test_iteration_58_flask_sqlalchemy_integration.py").read_text()
    phase = ast.parse((root / "app/services/campaign_phase.py").read_text())
    exported = {node.name for node in phase.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    tree = ast.parse(integration)
    imported = {alias.name for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
                and node.module == "app.services.campaign_phase" for alias in node.names}
    assert {"get_campaign_phase", "set_campaign_phase"} <= imported <= exported
    assert "get_current_phase" not in integration
    assert "set_current_phase" not in integration


def test_integration_suite_keeps_real_database_and_rollback_scenarios():
    root = Path(__file__).resolve().parents[1]
    text = (root / "tests/test_iteration_58_flask_sqlalchemy_integration.py").read_text()
    for marker in ("sqlite:///", "db.create_all()", "db.session.rollback()",
                   "materialize_selected_commitments()", "assert_selected_commitments_materialized()",
                   "campaign_id=2", "test_validation_failure_rolls_back_uncommitted_selection"):
        assert marker in text
