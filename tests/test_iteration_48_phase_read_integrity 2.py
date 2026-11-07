"""Regression tests for invalid persisted campaign phases (no Flask required)."""
import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]


def load_service(monkeypatch, *, stored=None, legacy=None, count=1):
    campaign = types.SimpleNamespace(id=7)
    config = types.SimpleNamespace(get=Mock(side_effect=lambda key: legacy if key == "phase" else stored), set=Mock())
    query = types.SimpleNamespace(limit=Mock(return_value=types.SimpleNamespace(count=Mock(return_value=count))))
    models = types.ModuleType("app.models")
    models.Campaign = types.SimpleNamespace(query=query)
    models.Config = config
    active = types.ModuleType("app.services.active_campaign")
    active.current_campaign = Mock(return_value=campaign)
    monkeypatch.setitem(sys.modules, "app", types.ModuleType("app"))
    monkeypatch.setitem(sys.modules, "app.services", types.ModuleType("app.services"))
    monkeypatch.setitem(sys.modules, "app.models", models)
    monkeypatch.setitem(sys.modules, "app.services.active_campaign", active)
    spec = importlib.util.spec_from_file_location("phase_under_test_48", ROOT / "app/services/campaign_phase.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, config, active


def test_valid_stored_phase_is_read(monkeypatch):
    for phase in ("first", "second", "final", "order"):
        module, _, _ = load_service(monkeypatch, stored=phase)
        assert module.get_campaign_phase() == phase


def test_unknown_stored_phase_falls_back_without_mutation(monkeypatch):
    for value in ("unexpected", "", 123):
        module, config, _ = load_service(monkeypatch, stored=value)
        assert module.get_campaign_phase() == "first"
        config.set.assert_not_called()


def test_invalid_legacy_phase_falls_back_without_mutation(monkeypatch):
    module, config, _ = load_service(monkeypatch, legacy="unexpected")
    assert module.get_campaign_phase() == "first"
    config.set.assert_not_called()


def test_valid_legacy_phase_used_only_for_single_campaign(monkeypatch):
    module, _, _ = load_service(monkeypatch, legacy="order", count=1)
    assert module.get_campaign_phase() == "order"
    module, _, _ = load_service(monkeypatch, legacy="order", count=2)
    assert module.get_campaign_phase() == "first"


def test_missing_campaign_defaults_to_first(monkeypatch):
    module, _, active = load_service(monkeypatch, stored="order")
    active.current_campaign.return_value = None
    assert module.get_campaign_phase() == "first"
