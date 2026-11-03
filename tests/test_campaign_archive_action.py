"""Structural regression tests; HTTP/integration tests still pending."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_archive_requires_final_export_and_expected_year():
    text = (ROOT / 'app/services/campaign_archive.py').read_text()
    assert "campaign.year != year" in text
    assert "final_order_generated_at" in text
    assert "final_order_excel" in text
    assert "destination.is_file()" in text


def test_archive_is_audited_and_no_other_year_activated():
    text = (ROOT / 'app/services/campaign_archive.py').read_text()
    assert "admin_campaign_archive" in text
    assert "campaign.status = 'archived'" in text
    assert 'Campaign(' not in text


def test_admin_form_requires_csrf_and_year_confirmation():
    page = (ROOT / 'templates/admin_campaign_history.html').read_text()
    routes = (ROOT / 'app/main/routes.py').read_text()
    assert 'csrf_token()' in page
    assert 'name="confirm_year"' in page
    assert 'methods=["POST"]' in routes
    assert '_ensure_admin()' in routes.split('def campaign_archive():', 1)[1].split('def campaign_history():', 1)[0]
