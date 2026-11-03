"""Regression: reverse proxy configuration must be applied AFTER config load."""
import ast
from pathlib import Path


def test_proxy_configuration_loaded_before_read():
    path = Path(__file__).resolve().parents[1] / 'app' / '__init__.py'
    source = path.read_text(encoding='utf-8')
    tree = ast.parse(source)
    factory = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'create_app')
    # Enforce ordering of the actual source statements (not comment placement).
    loaded = [node.lineno for node in ast.walk(factory)
              if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
              and node.func.attr in ('from_object', 'from_pyfile')]
    proxy_reads = [node.lineno for node in ast.walk(factory)
                   if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                   and node.func.attr == 'get' and node.args
                   and isinstance(node.args[0], ast.Constant)
                   and node.args[0].value == 'TRUSTED_PROXY_COUNT']
    assert len(loaded) == 2 and len(proxy_reads) == 1
    assert max(loaded) < proxy_reads[0]
