"""Prevent activation with only pending or historical-year approvals."""
import importlib.util
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / 'app/services/draft_activation_preflight.py'
spec = importlib.util.spec_from_file_location('annual_gate_72', SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def assess(**changes):
    counts = dict(product=85, campaign_participation=12, approved_with_document=0,
                  approved_without_document=0, user_vote=0, user_favorite=0, order=0)
    counts.update(changes)
    return module.evaluate_draft_activation(year=2027, counts=counts,
                                             database_findings=[], archived_years=[2026])

def test_pending_only_roster_cannot_activate():
    result = assess()
    assert not result['data_prepared']
    assert any('aprobado' in message for message in result['blockers'])

def test_approval_without_document_cannot_activate():
    result = assess(approved_without_document=1)
    assert not result['data_prepared']
    assert len(result['blockers']) == 2

def test_current_year_approval_satisfies_consent_gate():
    result = assess(approved_with_document=1)
    assert result['data_prepared']
    assert not result['activation_enabled']

def test_missing_roster_remains_blocked():
    result = assess(campaign_participation=0, approved_with_document=0)
    assert not result['data_prepared']
    assert len(result['blockers']) == 2
