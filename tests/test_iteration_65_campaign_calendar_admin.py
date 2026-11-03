"""Static route/UI regression checks; no Flask runtime required."""
import ast
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def test_admin_calendar_is_protected_and_scoped():
    tree = ast.parse((ROOT / 'app/main/routes.py').read_text())
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'manage_campaign_calendar')
    source = ast.get_source_segment((ROOT / 'app/main/routes.py').read_text(), node)
    assert '_ensure_admin()' in source
    assert 'db.session.get(Campaign, campaign_id)' in source
    assert "campaign.status in ('draft', 'legacy_active')" in source
    assert 'configure_campaign_window(campaign, start, end, commit=False)' in source
    assert 'db.session.rollback()' in source
    assert 'db.session.commit()' in source

def test_calendar_form_has_csrf_and_archive_read_only():
    page = (ROOT / 'templates/admin_campaign_calendar.html').read_text()
    assert 'csrf_token()' in page
    assert '{% if editable %}' in page
    assert 'type="date"' in page
    assert 'Solo lectura' in page or 'solo lectura' in page
    registry = (ROOT / 'templates/admin_campaigns.html').read_text()
    assert 'main.manage_campaign_calendar' in registry
