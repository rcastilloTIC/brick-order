from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]


def test_admin_draft_requires_auth_and_csrf():
    source = (ROOT/'app/main/routes.py').read_text()
    chunk = source.split('def campaign_draft():', 1)[1].split('@main_bp.route',1)[0]
    assert '_ensure_admin()' in chunk
    assert 'create_next_campaign_draft(' in chunk
    assert 'csrf_token()' in (ROOT/'templates/admin_campaign_history.html').read_text()


def test_drafts_are_inert():
    service = (ROOT/'app/services/campaign_registry.py').read_text()
    part = service.split('def create_next_campaign_draft(',1)[1]
    assert "status='draft'" in part
    assert "('archived', 'closed')" in part
    assert 'year <= max(c.year for c in campaigns)' in part
    policy = (ROOT/'app/services/active_campaign.py').read_text()
    assert "c.status == 'legacy_active'" in policy
    assert "if len(active) > 1 or len(drafts) > 1 or (active and drafts):" in policy
