"""No database required: guardrails that stop a premature annual reset."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_campaign_is_non_destructive():
    code = (ROOT / 'app/services/campaign_registry.py').read_text()
    assert 'delete(' not in code
    assert 'drop_all(' not in code
    assert 'second campaign before data isolation migration' in code

def test_admin_campaigns_are_read_only():
    code = (ROOT / 'app/main/routes.py').read_text()
    assert "@main_bp.route('/admin/campaigns', methods=['GET']" in code

def test_existing_annual_reset_is_blocked():
    code = (ROOT / 'app/main/routes.py').read_text()
    section = code.split('def clean_data():', 1)[1].split('@main_bp.route', 1)[0]
    assert 'abort(409' in section
