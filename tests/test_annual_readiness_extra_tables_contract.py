from pathlib import Path


def test_readiness_checks_all_campaign_owned_tables():
    source = (Path(__file__).resolve().parents[1] / 'app/services/annual_readiness.py').read_text()
    assert 'inspector.get_table_names()' in source
    assert "'campaign_id' not in columns" in source
    assert 'PRAGMA foreign_key_check' in source
    assert "'activation_enabled': False" in source
