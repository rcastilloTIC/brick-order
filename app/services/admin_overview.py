"""Read-only data for the administrator's control room (proposal A).

Shared by both editions. Everything edition-specific (the phase steps after
"order", the gate that must close before exporting, the edition module) is
passed in by that edition's own route, so this module never imports code from
the other edition. It performs no writes.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Iterable, List, Optional, Sequence, Tuple

from app import db
from app.models import ActionLog, CampaignParticipation, Product, User, UserVote
from app.services.active_campaign import current_campaign
from app.services.campaign_data import votes_query

BASE_STEPS: Tuple[Tuple[str, str], ...] = (
    ("first", "Primera votación"),
    ("second", "Segunda votación"),
    ("final", "Selección final"),
    ("order", "Pedido"),
)


def phase_rail(current_phase: str, steps: Sequence[Tuple[str, str]], order_finalized: bool) -> List[dict]:
    """Ordered steps with state done / current / todo, plus the export step."""
    keys = [key for key, _ in steps]
    current_index = keys.index(current_phase) if current_phase in keys else -1
    rail = []
    for index, (key, label) in enumerate(steps):
        if order_finalized or index < current_index:
            state = "done"
        elif index == current_index:
            state = "current"
        else:
            state = "todo"
        rail.append({"key": key, "label": label, "number": index + 1, "state": state})
    rail.append({"key": "exported", "label": "Pedido generado y archivo",
                 "number": len(steps) + 1, "state": "current" if order_finalized else "todo"})
    return rail


def _vote_commitment_total() -> float:
    """Committed amount from votes (used before the final selection exists)."""
    total = Decimal("0")
    rows = (votes_query().join(Product, Product.id == UserVote.product_id)
            .with_entities(UserVote.quantity, Product.price).all())
    for quantity, price in rows:
        total += Decimal(int(quantity or 0)) * Decimal(str(price or 0))
    return float(total)


def participant_counts(campaign_id: int) -> dict:
    rows = (db.session.query(CampaignParticipation.status, CampaignParticipation.signed_document)
            .join(User, User.id == CampaignParticipation.user_id)
            .filter(CampaignParticipation.campaign_id == campaign_id, User.is_admin.is_(False)).all())
    approved = sum(1 for status, doc in rows if status == "approved" and doc)
    to_review = sum(1 for status, doc in rows if doc and status != "approved")
    without_document = sum(1 for _, doc in rows if not doc)
    return {"approved": approved, "to_review": to_review, "without_document": without_document,
            "total": len(rows)}


def recent_activity(limit: int = 6) -> List[dict]:
    rows = (db.session.query(ActionLog, User.username)
            .join(User, User.id == ActionLog.user_id)
            .order_by(ActionLog.created_at.desc(), ActionLog.id.desc()).limit(limit).all())
    return [{"when": log.created_at, "who": username, "action": log.action, "detail": log.detail or ""}
            for log, username in rows]


def build_admin_overview(*, current_phase: str, steps: Sequence[Tuple[str, str]],
                         order_phases: Iterable[str], promoted_total: float, min_total: float,
                         order_finalized: bool, test_mode: bool, final_context: Optional[dict],
                         final_selection_limit: int, materialized: Optional[bool],
                         costs_configured: bool, payment_configured: bool,
                         edition_gate: Optional[dict] = None) -> dict:
    """Assemble the control-room view model. ``edition_gate`` is the edition's
    own pre-export condition: {"label": str, "done": bool, "detail": str}."""
    campaign = current_campaign()
    order_phases = set(order_phases)
    in_selection_or_order = current_phase == "final" or current_phase in order_phases

    if in_selection_or_order:
        amount = float(promoted_total or 0.0)
        amount_label = ("Pedidos efectivos" if current_phase in order_phases
                        else "Importe de las referencias seleccionadas")
    else:
        amount = _vote_commitment_total()
        amount_label = "Compromisos de voto"
    minimum = float(min_total or 0.0)
    percent = 0.0 if minimum <= 0 else max(0.0, min(100.0, amount * 100.0 / minimum))
    missing = max(0.0, minimum - amount)

    selection = None
    if current_phase == "final" and final_context:
        selection = {"count": int(final_context.get("selected_count") or 0),
                     "limit": int(final_context.get("limit") or final_selection_limit),
                     "ties": len(final_context.get("tie_breakers") or []),
                     "over_limit": bool(final_context.get("over_limit"))}
    elif current_phase in order_phases or order_finalized:
        count = (Product.query.filter_by(campaign_id=campaign.id, final_selected=True,
                                         final_disabled=False).count() if campaign else 0)
        selection = {"count": count, "limit": final_selection_limit, "ties": 0, "over_limit": False}

    checklist = []
    if current_phase in order_phases and not order_finalized:
        checklist.append({"label": "Compromisos seleccionados materializados en pedidos",
                          "done": bool(materialized), "detail": "" if materialized else "Revisa la fase de pedido"})
        minimum_ok = amount >= minimum
        checklist.append({"label": "Importe mínimo alcanzado",
                          "done": minimum_ok or test_mode,
                          "detail": "" if minimum_ok else (
                              "Modo de pruebas: se permite exportar" if test_mode
                              else f"Faltan {missing:,.2f} €".replace(",", "X").replace(".", ",").replace("X", "."))})
        if edition_gate:
            checklist.append(edition_gate)
        checklist.append({"label": "Impuestos y transporte configurados", "done": costs_configured, "detail": ""})
        checklist.append({"label": "IBAN y fecha límite de pago", "done": payment_configured, "detail": ""})

    return {
        "campaign": campaign,
        "rail": phase_rail(current_phase, steps, order_finalized),
        "amount": amount, "amount_label": amount_label, "minimum": minimum,
        "percent": round(percent, 1), "missing": missing, "minimum_met": amount >= minimum,
        "participants": participant_counts(campaign.id) if campaign else None,
        "selection": selection,
        "checklist": checklist,
        "activity": recent_activity(),
        "test_mode": test_mode,
    }
