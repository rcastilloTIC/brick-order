"""Runtime tests for strict active campaign registry validation."""
import importlib.util
import sys
import types
from pathlib import Path
import pytest

SOURCE = Path(__file__).resolve().parents[1] / 'app/services/active_campaign.py'

@pytest.mark.parametrize('statuses,expected', [
    ([], None), (['archived', 'draft'], None),
    (['archived', 'legacy_active'], 'legacy_active'),
    (['legacy_active', 'legacy_active'], 'error'),
    (['legacy_active', 'draft'], 'error'),
    (['draft', 'draft'], 'error'),
    (['legacy_active', 'unknown'], 'error'),
])
def test_registry_fails_closed(monkeypatch, statuses, expected):
    rows = [types.SimpleNamespace(status=status) for status in statuses]
    class Query:
        def all(self): return rows
    models = types.ModuleType('app.models')
    models.Campaign = types.SimpleNamespace(query=Query())
    models.CampaignParticipation = object
    monkeypatch.setitem(sys.modules, 'app.models', models)
    spec = importlib.util.spec_from_file_location('_active_campaign_test', SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if expected == 'error':
        with pytest.raises(RuntimeError): module.current_campaign()
    else:
        result = module.current_campaign()
        assert (result.status if result else None) == expected
