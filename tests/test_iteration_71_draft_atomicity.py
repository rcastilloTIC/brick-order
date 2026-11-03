"""Dependency-free regression tests for draft atomicity and strict date types."""
import importlib.util
import sys
import types
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch
import pytest

ROOT = Path(__file__).resolve().parents[1]

def load_calendar():
    spec = importlib.util.spec_from_file_location('calendar_71', ROOT / 'app/services/campaign_calendar.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

@pytest.mark.parametrize('start,end', [
    (datetime(2026, 10, 1), date(2027, 3, 1)),
    (date(2026, 10, 1), datetime(2027, 3, 1)),
])
def test_calendar_rejects_datetime_values(start, end):
    calendar = load_calendar()
    with pytest.raises(calendar.CampaignCalendarError, match='fechas'):
        calendar.validate_campaign_window(2026, start, end)

@pytest.mark.parametrize('failure', ['audit', 'commit'])
def test_draft_rolls_back_on_non_integrity_failure(failure):
    calls = []
    class Campaign:
        query = None
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)
            self.id = 17
    class Query:
        def all(self):
            return [Campaign(year=2025, status='archived')]
    Campaign.query = Query()
    def commit():
        calls.append('commit')
        if failure == 'commit':
            raise RuntimeError('commit failed')
    session = types.SimpleNamespace(add=lambda item: calls.append('add'),
                                    flush=lambda: calls.append('flush'),
                                    commit=commit, rollback=lambda: calls.append('rollback'))
    app = types.ModuleType('app')
    app.db = types.SimpleNamespace(session=session)
    models = types.ModuleType('app.models')
    models.Campaign = Campaign
    log = types.ModuleType('app.services.activity_log')
    def audit(*args):
        calls.append('audit')
        if failure == 'audit':
            raise RuntimeError('audit failed')
    log.log_user_action = audit
    sqlalchemy = types.ModuleType('sqlalchemy')
    exc = types.ModuleType('sqlalchemy.exc')
    class IntegrityError(Exception):
        pass
    exc.IntegrityError = IntegrityError
    modules = {'app': app, 'app.models': models, 'app.services': types.ModuleType('app.services'),
               'app.services.activity_log': log, 'sqlalchemy': sqlalchemy, 'sqlalchemy.exc': exc}
    with patch.dict(sys.modules, modules):
        spec = importlib.util.spec_from_file_location('registry_71', ROOT / 'app/services/campaign_registry.py')
        registry = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(registry)
        with pytest.raises(RuntimeError):
            registry.create_next_campaign_draft(year=2026, title='Campaña 2026', actor_id=3)
    assert calls[-1] == 'rollback'
    assert calls.count('rollback') == 1
    if failure == 'audit':
        assert 'commit' not in calls
