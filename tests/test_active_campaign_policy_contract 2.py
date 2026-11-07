"""Source-level guards; integration tests with Flask/database remain necessary."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_app_requires_membership_and_current_approval():
    source = (ROOT / 'app/__init__.py').read_text()
    assert 'membership is None' in source
    assert "membership.status != 'approved'" in source
    assert 'membership.signed_document' in source


def test_upload_and_approval_update_campaign_membership():
    auth = (ROOT / 'app/auth/routes.py').read_text()
    main = (ROOT / 'app/main/routes.py').read_text()
    assert 'submit_signed_document(membership, filename)' in auth
    assert 'review_signed_document(membership, current_user, approve=True)' in main


def test_multiple_campaigns_fail_closed():
    service = (ROOT / 'app/services/active_campaign.py').read_text()
    assert 'if len(active) > 1' in service
    assert 'raise RuntimeError' in service
