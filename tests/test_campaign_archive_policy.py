"""Runtime policy tests with fake SQLAlchemy models (no Flask required)."""
import importlib.util
import sys
import types
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / 'app/services/active_campaign.py'


def load_policy(monkeypatch, campaigns):
    class Query:
        def limit(self, n):
            assert n == 2
            return self
        def all(self):
            return campaigns[:2]

    class Campaign:
        query = Query()

    class Membership:
        query = None

    fake_app = types.ModuleType('app')
    fake_models = types.ModuleType('app.models')
    fake_models.Campaign = Campaign
    fake_models.CampaignParticipation = Membership
    monkeypatch.setitem(sys.modules, 'app', fake_app)
    monkeypatch.setitem(sys.modules, 'app.models', fake_models)
    spec = importlib.util.spec_from_file_location('tested_campaign_policy', MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_current_legacy_campaign_is_available(monkeypatch):
    campaign = types.SimpleNamespace(id=1, status='legacy_active')
    assert load_policy(monkeypatch, [campaign]).current_campaign() is campaign


@pytest.mark.parametrize('status', ['archived', 'closed', 'draft'])
def test_nonactive_campaign_fails_closed(monkeypatch, status):
    campaign = types.SimpleNamespace(id=1, status=status)
    policy = load_policy(monkeypatch, [campaign])
    assert policy.current_campaign() is None
    assert policy.allowed_to_participate(42) is False


def test_unknown_campaign_status_fails_closed(monkeypatch):
    policy = load_policy(monkeypatch, [types.SimpleNamespace(id=1, status=None)])
    with pytest.raises(RuntimeError, match='Unknown campaign status'):
        policy.current_campaign()
    with pytest.raises(RuntimeError, match='Unknown campaign status'):
        policy.allowed_to_participate(42)


def test_absent_campaign_fails_closed(monkeypatch):
    assert load_policy(monkeypatch, []).current_campaign() is None


def test_two_campaigns_remain_blocked(monkeypatch):
    campaigns = [types.SimpleNamespace(id=i, status='legacy_active') for i in (1, 2)]
    with pytest.raises(RuntimeError, match='Inconsistent campaign registry'):
        load_policy(monkeypatch, campaigns).current_campaign()
