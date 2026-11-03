"""Regression contracts for campaign-scoped mutation entry points."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_admin_mutations_check_membership():
    source = (ROOT / 'app/main/routes.py').read_text()
    for function, next_function in [('admin_update_order', 'admin_add_order'),
                                     ('admin_add_order', '_collect_user_votes')]:
        chunk = source.split('def ' + function + '():', 1)[1].split('\n@main_bp.route', 1)[0]
        assert 'require_campaign_participant(' in chunk


def test_participant_vote_mutations_check_membership():
    source = (ROOT / 'app/main/routes.py').read_text()
    for function in ('submit_vote', 'delete_vote'):
        chunk = source.split('def ' + function + '():', 1)[1].split('\n@main_bp.route', 1)[0]
        assert 'require_campaign_participant(current_user.id)' in chunk


def test_membership_guard_checks_campaign_and_approval():
    source = (ROOT / 'app/services/active_campaign.py').read_text()
    guard = source.split('def require_campaign_participant(', 1)[1]
    assert 'campaign_id=campaign.id' in guard
    assert 'user_id=user_id' in guard
    assert 'membership.status != "approved"' in guard
    assert 'not membership.signed_document' in guard
