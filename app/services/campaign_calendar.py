"""Calendar policy for non-overlapping October-to-March annual campaigns.

The campaign year is ALWAYS the start year, including January-March.
Dates are configurable and never cause automatic year switching.
"""
from datetime import date, datetime


class CampaignCalendarError(ValueError):
    pass


def validate_campaign_window(year: int, start: date, end: date) -> None:
    """Validate a campaign's configured season without imposing fixed days.

    A season starts in its named year and finishes in the following year.
    The October-March convention is informative, not a hard-coded boundary.
    """
    if isinstance(year, bool) or not isinstance(year, int) or not 2000 <= year <= 9998:
        raise CampaignCalendarError('Año de inicio inválido.')
    if (not isinstance(start, date) or not isinstance(end, date)
            or isinstance(start, datetime) or isinstance(end, datetime)):
        raise CampaignCalendarError('Las fechas deben ser fechas válidas.')
    if start.year != year or end.year != year + 1 or start >= end:
        raise CampaignCalendarError('La campaña debe comenzar en su año y terminar en el siguiente.')


def assert_no_window_overlap(start: date, end: date, other_windows) -> None:
    """Reject any shared calendar day across different annual campaigns.

    Windows are inclusive: a campaign ending on a date cannot share that
    date with the next campaign. Missing historical dates are not guessed.
    """
    for other_year, other_start, other_end in other_windows:
        if start <= other_end and other_start <= end:
            raise CampaignCalendarError(
                f'Las fechas se solapan con la campaña {other_year}.')


def other_campaign_windows(campaign_id: int):
    """Load configured windows of other years; reject incomplete history."""
    from app.models import Campaign
    windows = []
    for other in Campaign.query.filter(Campaign.id != campaign_id).all():
        window = read_campaign_window(other)
        if window is not None:
            windows.append((other.year, *window))
    return windows


def campaign_window_key(campaign_id: int, field: str) -> str:
    if isinstance(campaign_id, bool) or not isinstance(campaign_id, int) or campaign_id <= 0:
        raise CampaignCalendarError('Identificador de campaña inválido.')
    if field not in ('start', 'end'):
        raise CampaignCalendarError('Campo de fecha inválido.')
    return f'campaign_{campaign_id}_{field}_date'


def read_campaign_window(campaign):
    """Read dates for any campaign, including archived history; never global keys."""
    from app.models import Config
    values = [Config.get(campaign_window_key(campaign.id, field)) for field in ('start', 'end')]
    if values == [None, None]:
        return None
    if not all(values):
        raise CampaignCalendarError('La campaña tiene fechas incompletas.')
    try:
        start, end = (date.fromisoformat(value) for value in values)
    except (TypeError, ValueError) as exc:
        raise CampaignCalendarError('Las fechas guardadas no son válidas.') from exc
    validate_campaign_window(campaign.year, start, end)
    return start, end


def configure_campaign_window(campaign, start: date, end: date, *, commit=True):
    """Store both dates in the same transaction; no schema migration required.

    Existing archived campaigns may be inspected, but their dates are immutable.
    """
    from app import db
    from app.models import Config
    if campaign.status not in ('draft', 'legacy_active'):
        raise CampaignCalendarError('No se pueden modificar las fechas de una campaña finalizada.')
    validate_campaign_window(campaign.year, start, end)
    assert_no_window_overlap(start, end, other_campaign_windows(campaign.id))
    for field, value in (('start', start), ('end', end)):
        key = campaign_window_key(campaign.id, field)
        entry = Config.query.filter_by(key=key).first()
        if entry is None:
            entry = Config(key=key, value=value.isoformat())
        else:
            entry.value = value.isoformat()
        db.session.add(entry)
    if commit:
        db.session.commit()
