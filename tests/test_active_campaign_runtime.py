"""Runtime tests of campaign authorization, independent of Flask installation.

Import the policy with lightweight module doubles to exercise real branches,
not a source-code grep. Full HTTP/SQLAlchemy integration is still required.
"""
import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import patch
import pytest


class Denied(Exception):
    def __init__(self, status):
        self.status = status


def abort(status, **kwargs):
    raise Denied(status)


class Query:
    def __init__(self, rows):
        self.rows = rows

    def limit(self, size):
        return Query(self.rows[:size])

    def all(self):
        return self.rows

    def filter_by(self, **kwargs):
        return Query([r for r in self.rows if all(getattr(r, k) == v for k, v in kwargs.items())])

    def one_or_none(self):
        if len(self.rows) > 1:
            raise ValueError("Multiple memberships")
        return self.rows[0] if self.rows else None


def load_policy(campaigns, participations):
    models = types.ModuleType("app.models")
    models.Campaign = types.SimpleNamespace(query=Query(campaigns))
    models.CampaignParticipation = types.SimpleNamespace(query=Query(participations))
    app = types.ModuleType("app")
    app.__path__ = []
    flask = types.ModuleType("flask")
    flask.abort = abort
    file = Path(__file__).parents[1] / "app/services/active_campaign.py"
    spec = importlib.util.spec_from_file_location("policy_under_test", file)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"app": app, "app.models": models, "flask": flask}):
        spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def fake_flask():
    flask = types.ModuleType("flask")
    flask.abort = abort
    with patch.dict(sys.modules, {"flask": flask}):
        yield


def record(**kwargs):
    return types.SimpleNamespace(**kwargs)


def test_no_campaign_denies_mutation():
    policy = load_policy([], [])
    with pytest.raises(Denied) as exc:
        policy.require_campaign_participant(12)
    assert exc.value.status == 409
    assert policy.allowed_to_participate(12) is False


def test_multiple_campaigns_fail_closed():
    policy = load_policy([record(id=1, status="legacy_active"), record(id=2, status="legacy_active")], [])
    with pytest.raises(RuntimeError):
        policy.require_campaign_participant(12)


def test_missing_participation_denied():
    policy = load_policy([record(id=1, status="legacy_active")], [])
    with pytest.raises(Denied) as exc:
        policy.require_campaign_participant(12)
    assert exc.value.status == 403


@pytest.mark.parametrize("membership", [
    record(campaign_id=1, user_id=12, status="pending_commitment", signed_document=None),
    record(campaign_id=1, user_id=12, status="approved", signed_document=None),
    record(campaign_id=1, user_id=12, status="rejected", signed_document="x.pdf"),
])
def test_unapproved_commitments_denied(membership):
    policy = load_policy([record(id=1, status="legacy_active")], [membership])
    with pytest.raises(Denied) as exc:
        policy.require_campaign_participant(12)
    assert exc.value.status == 403


def test_approved_membership_passes_only_correct_campaign():
    policy = load_policy([record(id=1, status="legacy_active")], [record(campaign_id=1, user_id=12, status="approved", signed_document="signed.pdf")])
    assert policy.require_campaign_participant(12) is None
    assert policy.allowed_to_participate(12) is True
    with pytest.raises(Denied):
        policy.require_campaign_participant(13)
