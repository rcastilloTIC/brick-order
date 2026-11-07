import importlib.util
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / 'app/services/draft_activation_preflight.py'
spec = importlib.util.spec_from_file_location('draft_activation_preflight', SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def counts(**changes):
    data = dict(product=85, campaign_participation=20, approved_with_document=10, approved_without_document=0,
                user_vote=0, user_favorite=0, order=0)
    data.update(changes)
    return data


def check(**kwargs):
    return module.evaluate_draft_activation(year=2027, archived_years=[2026],
                                            database_findings=[], counts=counts(**kwargs))


def test_prepared_data_never_enables_activation():
    result = check()
    assert result['data_prepared'] is True
    assert result['activation_enabled'] is False
    assert not result['blockers']


def test_missing_catalog_and_participants_are_blocked():
    result = check(product=0, campaign_participation=0)
    assert len(result['blockers']) == 2
    assert not result['data_prepared']


def test_invalid_approval_and_premature_activity_are_blocked():
    result = check(approved_without_document=1, user_vote=2, user_favorite=1, order=3)
    assert len(result['blockers']) == 4


def test_archival_and_global_integrity_are_required():
    result = module.evaluate_draft_activation(year=2027, archived_years=[],
        database_findings=['orphan'], counts=counts())
    assert len(result['blockers']) == 2
    result = module.evaluate_draft_activation(year=2025, archived_years=[2026],
        database_findings=[], counts=counts())
    assert len(result['blockers']) == 1


def test_template_and_report_integrated():
    root = SOURCE.parents[2]
    assert "'draft_activation': draft_activation" in (root/'app/services/annual_readiness.py').read_text()
    assert 'assessment.blockers' in (root/'templates/admin_campaign_readiness.html').read_text()
