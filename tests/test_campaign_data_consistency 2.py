"""Behavioral tests for the shared campaign selection policy (dependency-free)."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_campaign_data_uses_single_authoritative_policy():
    source = (ROOT / "app/services/campaign_data.py").read_text()
    tree = ast.parse(source)
    imports = [node for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    assert any(node.module == "app.services.active_campaign" and any(a.name == "current_campaign" for a in node.names) for node in imports)
    assert "Campaign.query.limit(2)" not in source

def test_campaign_data_fails_closed_on_missing_and_multiple_campaigns():
    source = (ROOT / "app/services/campaign_data.py").read_text()
    tree = ast.parse(source)
    fn = next(x for x in tree.body if isinstance(x, ast.FunctionDef) and x.name == "active_campaign_id")
    calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call)]
    assert any(isinstance(c.func, ast.Name) and c.func.id == 'current_campaign' for c in calls)
    assert sum(isinstance(c.func, ast.Name) and c.func.id == 'abort' for c in calls) == 2
