"""Execute the actual transition handler with injected failures, without Flask deps."""
import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_handler(namespace):
    tree = ast.parse((ROOT / 'app/main/routes.py').read_text())
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'advance_order_phase')
    node.decorator_list = []
    module = ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[]))
    exec(compile(module, '<advance_order_phase>', 'exec'), namespace)
    return namespace['advance_order_phase']


@pytest.mark.parametrize('failure', ['selection', 'materialization', 'phase', 'commit'])
def test_failure_rolls_back_without_completing_transition(failure):
    events = []
    session = SimpleNamespace(commit=lambda: (events.append('commit'), (_ for _ in ()).throw(RuntimeError('commit failed')))[-1] if failure == 'commit' else events.append('commit'),
                              rollback=lambda: events.append('rollback'))
    # The materialization import in the handler resolves to the real module.
    # Compile a copy of the handler with only that import replaced by a no-op.
    source = (ROOT / 'app/main/routes.py').read_text()
    tree = ast.parse(source)
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'advance_order_phase')
    node.decorator_list = []
    node.body = [n for n in node.body if not (isinstance(n, ast.ImportFrom) and n.module == 'app.services.order_materialization')]
    node = ast.fix_missing_locations(node)
    def step(name, value):
        events.append(name)
        if name == failure:
            raise RuntimeError('injected ' + name)
        return value
    ns = dict(
        _ensure_admin=lambda: None, get_current_phase=lambda: 'final',
        get_limit_configuration=lambda: {'final_selection_limit': 85},
        compute_final_selection=lambda **kw: step('selection', {'tie_breakers': [], 'over_limit': [], 'selected_count': 85, 'limit': 85}) if kw.get('commit') is False else {'tie_breakers': [], 'over_limit': [], 'selected_count': 85, 'limit': 85},
        _attempt_phase_backup=lambda *args: events.append('backup'),
        materialize_selected_commitments=lambda: step('materialization', (1, 2)),
        assert_selected_commitments_materialized=lambda: events.append('verify'),
        set_current_phase=lambda *args, **kw: step('phase', None),
        db=SimpleNamespace(session=session),
        current_app=SimpleNamespace(logger=SimpleNamespace(exception=lambda *args: None)),
        flash=lambda *args: events.append('flash'),
        _admin_redirect=lambda **kw: 'failure_redirect',
        redirect=lambda url: 'success_redirect', url_for=lambda *args, **kw: '/admin',
    )
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])), '<handler>', 'exec'), ns)
    assert ns['advance_order_phase']() == 'failure_redirect'
    assert events.count('rollback') == 1
    assert events.count('commit') == (1 if failure == 'commit' else 0)
    assert events[-1] == 'flash'


def test_success_commits_once_without_rollback():
    events = []
    tree = ast.parse((ROOT / 'app/main/routes.py').read_text())
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'advance_order_phase')
    node.decorator_list = []
    node.body = [n for n in node.body if not (isinstance(n, ast.ImportFrom) and n.module == 'app.services.order_materialization')]
    summary = {'tie_breakers': [], 'over_limit': [], 'selected_count': 85, 'limit': 85}
    ns = dict(_ensure_admin=lambda: None, get_current_phase=lambda: 'final',
              get_limit_configuration=lambda: {'final_selection_limit': 85},
              compute_final_selection=lambda **kw: summary,
              _attempt_phase_backup=lambda *a: events.append('backup'),
              materialize_selected_commitments=lambda: (2, 4),
              assert_selected_commitments_materialized=lambda: events.append('verify'),
              set_current_phase=lambda *a, **kw: events.append('phase'),
              db=SimpleNamespace(session=SimpleNamespace(commit=lambda: events.append('commit'), rollback=lambda: events.append('rollback'))),
              flash=lambda *a: None, redirect=lambda url: 'ok', url_for=lambda *a, **kw: '/admin')
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])), '<handler>', 'exec'), ns)
    assert ns['advance_order_phase']() == 'ok'
    assert events == ['backup', 'verify', 'phase', 'commit']
