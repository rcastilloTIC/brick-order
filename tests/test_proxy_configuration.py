"""Proxy safety regression tests without application dependencies."""
import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_default_proxy_trust_is_zero():
    text = (ROOT / 'config.py').read_text()
    assert re.search(r"TRUSTED_PROXY_COUNT\s*=\s*int\(os.getenv\('TRUSTED_PROXY_COUNT', '0'\)\)", text)


def test_proxy_wrapper_is_conditional():
    tree = ast.parse((ROOT / 'app/__init__.py').read_text())
    factory = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'create_app')
    if_blocks = [n for n in factory.body if isinstance(n, ast.If)]
    branches = [n for n in if_blocks if isinstance(n.test, ast.Name) and n.test.id == 'proxy_count']
    assert len(branches) == 1
    assert any(isinstance(n, ast.Assign) and isinstance(n.value, ast.Call)
               and isinstance(n.value.func, ast.Name) and n.value.func.id == 'ProxyFix'
               for n in branches[0].body)
    assert not any(isinstance(n, ast.Assign) and isinstance(n.value, ast.Call)
                   and isinstance(n.value.func, ast.Name) and n.value.func.id == 'ProxyFix'
                   for n in factory.body)


def test_trust_bounds_are_checked():
    source = (ROOT / 'app/__init__.py').read_text()
    assert '0 <= proxy_count <= 2' in source
    assert "raise ValueError('TRUSTED_PROXY_COUNT must be an integer from 0 to 2')" in source
