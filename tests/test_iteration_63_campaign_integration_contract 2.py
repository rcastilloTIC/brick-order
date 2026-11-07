"""Offline regression contract for the campaign integration scenarios."""
import ast
from pathlib import Path

TEST_FILE = Path(__file__).with_name("test_iteration_58_flask_sqlalchemy_integration.py")


def test_registry_guard_cases_are_exercised_by_real_service():
    source = TEST_FILE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    tests = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    case = tests["test_inconsistent_campaign_registry_blocks_materialization"]
    calls = [n for n in ast.walk(case) if isinstance(n, ast.Call)]
    assert any(isinstance(c.func, ast.Name) and c.func.id == "materialize_selected_commitments" for c in calls)
    assert "legacy_active" in source and "draft" in source
    assert any(isinstance(c.func, ast.Attribute) and c.func.attr == "rollback" for c in calls)


def test_archived_phase_isolation_is_covered():
    tree = ast.parse(TEST_FILE.read_text(encoding="utf-8"))
    tests = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    case = tests["test_committed_phase_is_isolated_from_archived_campaign"]
    called = {n.func.id for n in ast.walk(case) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert {"set_campaign_phase", "get_campaign_phase", "phase_config_key"} <= called
