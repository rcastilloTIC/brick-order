import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'app/main/routes.py').read_text()
TREE = ast.parse(SOURCE)

def function(name):
    return next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == name)

def test_public_schedule_does_not_read_extension_dates_or_enter_extension():
    code = ast.get_source_segment(SOURCE, function('_auto_advance_phase_from_schedule'))
    assert 'extension_start_date' not in code
    assert 'extension_end_date' not in code
    assert 'target = "extension"' not in code
    assert 'minimum' in code

def test_public_dates_form_does_not_write_extension_settings():
    code = ast.get_source_segment(SOURCE, function('set_dates'))
    assert 'extension_start_date' not in code
    assert 'extension_end_date' not in code
    template = (ROOT / 'templates/set_dates.html').read_text()
    assert 'extension_start_date' not in template
    assert 'extension_end_date' not in template
