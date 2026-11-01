"""Helpers to manage dynamic configuration such as the temporary test mode."""

from __future__ import annotations

from typing import Dict

from flask import current_app

from app.models import Config
from app.services.campaign_settings import get_annual_setting

TEST_MODE_KEY = "test_mode"

_TEST_MODE_LIMITS = {
    "phase_one_order_limit": 50.0,
    "max_refs_phase_one": 3,
    "max_refs_phase_two": 6,
    "final_selection_limit": 10,
}


def is_test_mode_enabled() -> bool:
    """Return True when the admin has enabled the test mode."""
    # Annual setting: a test mode enabled for one campaign never leaks into
    # another year (legacy global key is read only for single-campaign DBs).
    return (get_annual_setting(TEST_MODE_KEY) or "").lower() in {"1", "true", "yes", "on"}


def get_limit_configuration(*, test_mode: bool | None = None) -> Dict[str, float | int]:
    """
    Provide the active limits for phase/order/final selection.

    Values default to the standard configuration but are overridden when the
    test mode flag is enabled.
    """
    limits = {
        "phase_one_order_limit": float(
            current_app.config.get("PHASE_ONE_ORDER_LIMIT", 235)
        ),
        "max_refs_phase_one": int(
            current_app.config.get("MAX_REFERENCES_PER_USER", 10)
        ),
        "max_refs_phase_two": int(
            current_app.config.get("PHASE_TWO_REFERENCE_LIMIT", 20)
        ),
        "final_selection_limit": int(
            current_app.config.get("FINAL_SELECTION_LIMIT", 85)
        ),
    }

    # The administration form persists these values per campaign. Never read
    # global values from an archived year when a new campaign is active.
    for name, caster in (
        ("phase_one_order_limit", float),
        ("final_selection_limit", int),
    ):
        configured = get_annual_setting("limit_" + name)
        if configured is not None:
            try:
                parsed = caster(configured)
                if name == "phase_one_order_limit":
                    from math import isfinite
                    valid = isfinite(parsed) and parsed > 0
                else:
                    valid = 1 <= parsed <= 1000 and str(configured).strip() == str(parsed)
                if not valid:
                    raise ValueError("Invalid saved annual limit")
                limits[name] = parsed
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError("Invalid annual limit: " + name) from exc

    # Reference caps not yet exposed in the annual admin form use application
    # defaults, not legacy global Config rows from another campaign.

    active_test_mode = test_mode if test_mode is not None else is_test_mode_enabled()

    if active_test_mode:
        limits.update(_TEST_MODE_LIMITS)

    return limits
