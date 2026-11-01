"""Annual phase storage: never inherit the phase from an archived campaign."""
from app.models import Campaign, Config
from app.services.active_campaign import current_campaign


def phase_config_key(campaign_id: int) -> str:
    if not isinstance(campaign_id, int) or isinstance(campaign_id, bool) or campaign_id <= 0:
        raise ValueError("Invalid campaign id")
    return f"phase_campaign_{campaign_id}"


PHASES = frozenset({"first", "second", "final", "order"})


def get_campaign_phase() -> str:
    campaign = current_campaign()
    if campaign is None:
        return "first"
    saved = Config.get(phase_config_key(campaign.id))
    if saved in PHASES:
        return saved
    if saved is not None:
        # An invalid stored value must never become an active public phase.
        # Leave the historical record untouched for manual inspection.
        return "first"
    # Backward compatibility only for a database with exactly one campaign.
    # A future campaign must NEVER inherit the last global phase (e.g. order).
    if Campaign.query.limit(2).count() == 1:
        legacy_phase = Config.get("phase")
        return legacy_phase if legacy_phase in PHASES else "first"
    return "first"


def set_campaign_phase(phase: str, *, commit: bool = True) -> None:
    # Only supported campaign phases may be persisted.
    if not isinstance(phase, str) or phase not in PHASES:
        raise ValueError('Unsupported public campaign phase')
    campaign = current_campaign()
    if campaign is None:
        raise ValueError("No active campaign")
    Config.set(phase_config_key(campaign.id), phase, commit=commit)
