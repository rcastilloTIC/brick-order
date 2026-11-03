import ast
from pathlib import Path

def test_draft_import_reuses_annual_enrolment_without_password_reset():
    root = Path(__file__).resolve().parents[1]
    source = (root / 'app/main/routes.py').read_text()
    tree = ast.parse(source)
    importer = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_handle_users_csv_upload')
    body = ast.get_source_segment(source, importer)
    assert 'draft_campaign_id=None' in body
    assert "status='draft'" in body
    assert 'enroll_existing_user(registered_campaign.id, user.id)' in body
    assert 'if is_new:' in body
    assert body.count('user.set_password(') == 1
    assert 'user.set_password(raw_password)' in body
    assert 'if user and user.is_admin:' in body

def test_draft_route_requires_admin_and_rechecks_status():
    root = Path(__file__).resolve().parents[1]
    source = (root / 'app/main/routes.py').read_text()
    tree = ast.parse(source)
    route = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'draft_participants')
    body = ast.get_source_segment(source, route)
    assert '_ensure_admin()' in body
    assert "status='draft'" in body
    assert '_handle_users_csv_upload(draft_campaign_id=campaign_id)' in body
    template = (root / 'templates/admin_campaign_history.html').read_text()
    assert "url_for('main.draft_participants', campaign_id=draft.id)" in template
