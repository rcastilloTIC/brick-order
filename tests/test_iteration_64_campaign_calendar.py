"""Dependency-free checks for the annual calendar contract."""
import importlib.util
from datetime import date
from pathlib import Path
import pytest

path = Path(__file__).resolve().parents[1] / 'app/services/campaign_calendar.py'
spec = importlib.util.spec_from_file_location('campaign_calendar_policy', path)
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)


def test_october_to_march_uses_start_year():
    policy.validate_campaign_window(2026, date(2026, 10, 18), date(2027, 3, 22))


def test_dates_can_vary_between_years():
    policy.validate_campaign_window(2025, date(2025, 9, 30), date(2026, 4, 8))
    policy.validate_campaign_window(2026, date(2026, 11, 2), date(2027, 2, 28))


@pytest.mark.parametrize('year,start,end', [
    (2027, date(2026, 10, 1), date(2027, 3, 1)),
    (2026, date(2026, 10, 1), date(2026, 12, 31)),
    (2026, date(2026, 10, 1), date(2028, 3, 1)),
    (True, date(2026, 10, 1), date(2027, 3, 1)),
])
def test_invalid_years_rejected(year, start, end):
    with pytest.raises(policy.CampaignCalendarError):
        policy.validate_campaign_window(year, start, end)


def test_campaign_dates_are_scoped_to_id():
    assert policy.campaign_window_key(3, 'start') == 'campaign_3_start_date'
    assert policy.campaign_window_key(4, 'start') != policy.campaign_window_key(3, 'start')
    with pytest.raises(policy.CampaignCalendarError):
        policy.campaign_window_key(3, 'other')
