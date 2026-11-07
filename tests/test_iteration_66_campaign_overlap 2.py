"""Pure policy and integration contract for non-overlapping annual seasons."""
import importlib.util
from datetime import date
from pathlib import Path
import pytest
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('annual_calendar', ROOT / 'app/services/campaign_calendar.py')
calendar = importlib.util.module_from_spec(spec)
spec.loader.exec_module(calendar)


def test_separate_october_to_march_campaigns():
    calendar.assert_no_window_overlap(date(2026, 10, 20), date(2027, 3, 15), [
        (2025, date(2025, 10, 15), date(2026, 3, 20))])


def test_overlap_even_if_years_are_distinct():
    with pytest.raises(calendar.CampaignCalendarError, match='2025'):
        calendar.assert_no_window_overlap(date(2026, 3, 10), date(2027, 3, 20), [
            (2025, date(2025, 10, 15), date(2026, 3, 20))])


def test_shared_end_day_is_overlap():
    with pytest.raises(calendar.CampaignCalendarError):
        calendar.assert_no_window_overlap(date(2026, 3, 20), date(2027, 3, 20), [
            (2025, date(2025, 10, 15), date(2026, 3, 20))])


def test_empty_history_is_allowed():
    calendar.assert_no_window_overlap(date(2026, 10, 20), date(2027, 3, 15), [])


def test_save_and_activation_enforce_overlap_policy():
    save = (ROOT / 'app/services/campaign_calendar.py').read_text()
    activation = (ROOT / 'app/services/campaign_activation.py').read_text()
    assert 'assert_no_window_overlap(start, end, other_campaign_windows(campaign.id))' in save
    assert 'assert_no_window_overlap(*draft_window, other_campaign_windows(drafts[0].id))' in activation
    assert 'if draft_window is None:' in activation
