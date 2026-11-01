"""Campaign-specific financial and final-export settings.

Legacy global keys are read only for a genuinely single-campaign database.
All writes go to the active campaign's namespace; never leak prior years.
"""
from app.models import Campaign, Config
from app.services.active_campaign import current_campaign

ANNUAL_KEYS = frozenset({
    "order_tax_percent", "order_shipping_amount", "limit_minimum_total",
    "limit_phase_one_order_limit", "limit_final_selection_limit",
    "final_order_excel", "final_order_piece_pdf", "final_order_user_pdf",
    "final_order_generated_at", "final_order_last_tax", "final_order_last_shipping",
    "final_order_payment_iban", "final_order_payment_due_date",
    "voting_start", "voting_end", "second_phase_date",
    "order_deadline",
    "commitment_pdf",
    "test_mode",
})


def annual_key(key: str, campaign_id: int) -> str:
    if key not in ANNUAL_KEYS:
        raise ValueError(f"Not an annual setting: {key}")
    if isinstance(campaign_id, bool) or not isinstance(campaign_id, int) or campaign_id <= 0:
        raise ValueError("Invalid campaign id")
    return f"annual_{campaign_id}_{key}"


def get_annual_setting(key: str):
    campaign = current_campaign()
    if campaign is None:
        return None
    value = Config.get(annual_key(key, campaign.id))
    if value is not None:
        return value
    # No legacy fallback when any prior campaign exists.
    if Campaign.query.limit(2).count() == 1:
        return Config.get(key)
    return None


def set_annual_setting(key: str, value):
    campaign = current_campaign()
    if campaign is None:
        raise ValueError("No active campaign for annual settings")
    Config.set(annual_key(key, campaign.id), value)
