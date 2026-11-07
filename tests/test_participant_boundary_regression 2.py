"""Regression contracts for campaign-aware participant endpoints.

These tests inspect the function AST rather than relying on a running Flask
app; HTTP integration tests are still required before release.
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _function(filename, function):
    module = ast.parse((ROOT / filename).read_text(encoding="utf8"))
    return next(node for node in ast.walk(module) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function)


def _calls_guard(node):
    return any(isinstance(child, ast.Call) and isinstance(child.func, ast.Name) and child.func.id == 'require_campaign_participant' for child in ast.walk(node))


def test_favorites_enforce_annual_membership():
    assert _calls_guard(_function('app/main/routes.py', 'toggle_favorite'))


def test_order_pdf_enforces_annual_membership():
    assert _calls_guard(_function('app/main/routes.py', 'download_user_order_pdf'))


def test_dashboard_uses_annual_membership():
    assert _calls_guard(_function('app/main/routes.py', 'user_dashboard'))


def test_no_account_level_fallback_when_campaign_missing():
    body = ast.get_source_segment((ROOT / 'app/__init__.py').read_text(), _function('app/__init__.py', 'enforce_user_onboarding'))
    assert 'current_user.declaration_validated' not in body
    assert 'current_user.declaration_file' not in body
