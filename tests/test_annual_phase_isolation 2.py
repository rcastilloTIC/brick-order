import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_phase_service_is_syntax_valid():
    ast.parse((ROOT / "app/services/campaign_phase.py").read_text())


def test_global_phase_reads_no_longer_in_operational_routes():
    for path in ("app/main/routes.py", "app/services/order_exports.py", "app/services/backups.py"):
        code = (ROOT / path).read_text()
        assert 'Config.get("phase")' not in code, path
        assert 'Config.set("phase",' not in code, path
        assert "get_campaign_phase" in code or "set_campaign_phase" in code


def test_legacy_fallback_only_with_single_campaign():
    src = (ROOT / "app/services/campaign_phase.py").read_text()
    assert 'Campaign.query.limit(2).count() == 1' in src
    assert 'phase_config_key(campaign.id)' in src
