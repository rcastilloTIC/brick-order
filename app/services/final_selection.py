"""Utilities to aggregate votes and compute/summarise the final 85 references."""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Dict, FrozenSet, Iterable, List, Set, Tuple

from sqlalchemy import asc, desc, func

from app import db
from app.models import Product, UserVote
from app.services.campaign_data import active_campaign_id, products_query

AggregateDict = Dict[int, Dict[str, float]]


@dataclass(frozen=True)
class FinalSelectionResult:
    limit: int
    selected_ids: FrozenSet[int]
    promoted_ids: FrozenSet[int]
    tie_breakers: List[Dict[str, object]]

    def to_dict(self) -> Dict[str, object]:
        selected_count = len(self.selected_ids)
        return {
            "limit": self.limit,
            "selected_count": selected_count,
            "promoted_count": len(self.promoted_ids),
            "tie_breakers": self.tie_breakers,
            "over_limit": selected_count > self.limit,
        }


def get_vote_aggregates() -> AggregateDict:
    """Return aggregate vote information per product."""
    aggregates: AggregateDict = {}
    rows = (
        db.session.query(
            UserVote.product_id.label("product_id"),
            func.coalesce(func.sum(UserVote.quantity), 0).label("total_quantity"),
            func.coalesce(func.count(UserVote.id), 0).label("num_votes"),
            func.coalesce(
                func.sum(UserVote.quantity * func.coalesce(Product.price, 0)), 0
            ).label("total_amount"),
        )
        .join(Product, Product.id == UserVote.product_id)
        .filter(UserVote.campaign_id == active_campaign_id())
        .filter(Product.campaign_id == active_campaign_id())
        .filter(UserVote.campaign_id == active_campaign_id())
        .group_by(UserVote.product_id)
        .all()
    )

    for row in rows:
        aggregates[row.product_id] = {
            "total_quantity": float(row.total_quantity or 0),
            "num_votes": int(row.num_votes or 0),
            "total_amount": float(row.total_amount or 0),
        }

    return aggregates


def compute_final_selection(limit: int = 85, *, persist: bool = True, commit: bool = True) -> Dict[str, object]:
    """
    Evaluate (and optionally persist) the final selection respecting the given cap.

    When ``persist`` is False no database writes are performed, making it safe to
    call from read-only contexts such as dashboards.
    """
    result = _determine_final_selection(limit)
    if persist:
        _persist_final_selection(result, commit=commit)
    return result.to_dict()


def get_final_selection_snapshot(limit: int = 85) -> Dict[str, object]:
    """Helper to obtain the current selection summary without writing to the DB."""
    return compute_final_selection(limit=limit, persist=False)


def get_neutral_ranking(limit: int = 85) -> Dict[str, object]:
    """Return the neutral ranking list for admin review."""
    if limit <= 0:
        raise ValueError("El límite de referencias finales debe ser mayor que 0")

    aggregates = get_vote_aggregates()
    locked_ids = _fetch_locked_ids()
    disabled_ids = {row.id for row in products_query().with_entities(Product.id).filter(Product.final_disabled.is_(True)).all()}

    locked_rows = []
    if locked_ids:
        locked_rows = (
            products_query().with_entities(
                Product.id,
                Product.reference,
                Product.name,
                Product.image_url,
                Product.color_bl,
            )
            .filter(Product.id.in_(locked_ids))
            .all()
        )

    locked_active = []
    locked_disabled = []
    for row in locked_rows:
        totals = aggregates.get(row.id, {"num_votes": 0, "total_quantity": 0.0, "total_amount": 0.0})
        entry = _build_neutral_row(row, totals, score=0.0)
        entry["is_locked"] = True
        if row.id in disabled_ids:
            locked_disabled.append(entry)
        else:
            locked_active.append(entry)

    ranked_rows = []
    if aggregates:
        scored_rows = _build_neutral_scores(
            products_query().with_entities(
                Product.id,
                Product.reference,
                Product.name,
                Product.image_url,
                Product.color_bl,
            )
            .filter(Product.campaign_id == active_campaign_id())
        .filter(Product.id.in_(aggregates.keys()))
            .all(),
            aggregates,
        )
        scored_rows.sort(
            key=lambda item: (
                -item["score"],
                -item["votes"],
                -item["amount_total"],
                item["reference"],
            )
        )
        ranked_rows = scored_rows

    active_ranked = [
        row for row in ranked_rows
        if row["id"] not in locked_ids and row["id"] not in disabled_ids
    ]
    disabled_ranked = [
        row for row in ranked_rows
        if row["id"] not in locked_ids and row["id"] in disabled_ids
    ]

    active_list = sorted(locked_active, key=lambda r: r["reference"]) + active_ranked
    disabled_list = sorted(locked_disabled, key=lambda r: r["reference"]) + disabled_ranked

    rows = []
    position = 1
    for row in active_list:
        row["position"] = position
        row["within_limit"] = position <= limit
        row["is_disabled"] = False
        rows.append(row)
        position += 1
    for row in disabled_list:
        row["position"] = position
        row["within_limit"] = False
        row["is_disabled"] = True
        rows.append(row)
        position += 1

    return {
        "limit": limit,
        "rows": rows,
        "active_count": len(active_list),
        "disabled_count": len(disabled_list),
    }


def get_phase_two_selection_snapshot(limit: int = 85) -> Dict[str, object]:
    """Return the ranked phase 2 selection without writing to the DB."""
    return _determine_phase_two_selection(limit)


def _build_neutral_row(row, totals, score: float) -> Dict[str, object]:
    return {
        "id": row.id,
        "reference": row.reference or "",
        "name": row.name,
        "image_url": row.image_url,
        "color_bl": row.color_bl,
        "votes": int(totals.get("num_votes", 0) or 0),
        "qty_total": float(totals.get("total_quantity", 0) or 0),
        "amount_total": float(totals.get("total_amount", 0) or 0),
        "score": float(score or 0),
        "is_locked": False,
    }


def _build_neutral_scores(rows, aggregates: AggregateDict) -> List[Dict[str, object]]:
    scored_rows = []
    max_votes = 0
    max_qty = 0.0
    max_cost_log = 0.0

    for row in rows:
        totals = aggregates.get(row.id, {})
        votes = int(totals.get("num_votes", 0) or 0)
        qty_total = float(totals.get("total_quantity", 0) or 0)
        amount_total = float(totals.get("total_amount", 0) or 0)
        cost_per_piece = (amount_total / qty_total) if qty_total else 0.0
        cost_log = math.log1p(cost_per_piece)

        max_votes = max(max_votes, votes)
        max_qty = max(max_qty, qty_total)
        max_cost_log = max(max_cost_log, cost_log)

        scored_rows.append(
            {
                "id": row.id,
                "reference": row.reference or "",
                "name": row.name,
                "image_url": row.image_url,
                "color_bl": row.color_bl,
                "votes": votes,
                "qty_total": qty_total,
                "amount_total": amount_total,
                "cost_log": cost_log,
            }
        )

    max_votes = max_votes or 1
    max_qty = max_qty or 1.0
    max_cost_log = max_cost_log or 1.0

    for row in scored_rows:
        votes_norm = row["votes"] / max_votes
        qty_norm = row["qty_total"] / max_qty
        cost_norm = row["cost_log"] / max_cost_log
        row["score"] = 0.40 * votes_norm + 0.35 * qty_norm + 0.25 * cost_norm

    return scored_rows


def _determine_final_selection(limit: int) -> FinalSelectionResult:
    if limit <= 0:
        raise ValueError("El límite de referencias finales debe ser mayor que 0")

    locked_ids = _fetch_locked_ids()
    selected_ids: Set[int] = set(locked_ids)
    remaining_slots = max(limit - len(locked_ids), 0)

    tie_breakers: List[Dict[str, object]] = []
    cutoff_metrics: Tuple[float, float, float, float, str] | None = None
    filled_slots = 0

    disabled_ids = _fetch_disabled_ids()
    for row in _iter_ranked_products(exclude_ids=selected_ids | disabled_ids):
        if remaining_slots and filled_slots < remaining_slots:
            selected_ids.add(row["id"])
            filled_slots += 1
            cutoff_metrics = row["metrics"]
            continue

        # Once the cap is reached, detect ties sharing the same vote metrics.
        if remaining_slots and cutoff_metrics and row["metrics"][:3] == cutoff_metrics[:3]:
            tie_breakers.append(_serialize_tie_candidate(row))
            continue

        break

    return FinalSelectionResult(
        limit=limit,
        selected_ids=frozenset(selected_ids),
        promoted_ids=frozenset(locked_ids),
        tie_breakers=tie_breakers,
    )


def _persist_final_selection(result: FinalSelectionResult, *, commit: bool = True) -> None:
    """Apply the computed selection to the database."""
    products_query().filter(Product.final_selected.is_(True)).update(
        {Product.final_selected: False}, synchronize_session=False
    )
    if result.selected_ids:
        products_query().filter(Product.id.in_(result.selected_ids)).update(
            {Product.final_selected: True}, synchronize_session=False
        )
    if commit:
        db.session.commit()


def _fetch_promoted_ids() -> Set[int]:
    rows = (
        products_query().with_entities(Product.id)
        .filter(Product.final_promoted.is_(True))
        .filter(Product.final_disabled.is_(False))
        .all()
    )
    return {row.id for row in rows}


def _fetch_locked_ids() -> Set[int]:
    rows = (
        products_query().with_entities(Product.id)
        .filter(Product.is_locked.is_(True))
        .all()
    )
    return {row.id for row in rows}


def _fetch_disabled_ids() -> Set[int]:
    rows = (
        products_query().with_entities(Product.id)
        .filter(Product.final_disabled.is_(True))
        .all()
    )
    return {row.id for row in rows}


def _fetch_voted_product_ids() -> Set[int]:
    rows = (
        db.session.query(UserVote.product_id)
        .filter(UserVote.campaign_id == active_campaign_id())
        .group_by(UserVote.product_id)
        .all()
    )
    return {row.product_id for row in rows}


def _iter_ranked_products(
    *, exclude_ids: Iterable[int]
) -> Iterable[Dict[str, object]]:
    exclude_set = set(exclude_ids)
    aggregates = get_vote_aggregates()
    if not aggregates:
        return []

    rows = (
        db.session.query(
            Product.id,
            Product.reference,
            Product.name,
            Product.image_url,
            Product.color_bl,
        )
        .filter(Product.campaign_id == active_campaign_id())
        .filter(Product.id.in_(aggregates.keys()))
        .filter(Product.final_disabled.is_(False))
        .all()
    )

    scored_rows = _build_neutral_scores(rows, aggregates)
    scored_rows.sort(
        key=lambda item: (
            -item["score"],
            -item["votes"],
            -item["amount_total"],
            item["reference"],
        )
    )

    for row in scored_rows:
        if row["id"] in exclude_set:
            continue
        totals = {
            "total_quantity": row["qty_total"],
            "total_amount": row["amount_total"],
            "num_votes": row["votes"],
        }
        metrics = (
            row["score"],
            row["votes"],
            row["amount_total"],
            row["reference"],
        )
        yield {
            "id": row["id"],
            "reference": row["reference"],
            "name": row["name"],
            "totals": totals,
            "metrics": metrics,
        }


def _serialize_tie_candidate(row: Dict[str, object]) -> Dict[str, object]:
    totals = row["totals"]
    return {
        "id": row["id"],
        "reference": row["reference"],
        "name": row["name"],
        "total_quantity": totals["total_quantity"],
        "total_amount": totals["total_amount"],
        "num_votes": totals["num_votes"],
    }


def _determine_phase_two_selection(limit: int) -> Dict[str, object]:
    if limit <= 0:
        raise ValueError("El límite de referencias finales debe ser mayor que 0")

    locked_ids = _fetch_locked_ids()
    aggregates = get_vote_aggregates()
    if not aggregates:
        return {
            "limit": limit,
            "locked_ids": locked_ids,
            "selected_ids": locked_ids,
            "selected_voted_ids": set(),
            "ranked_ids": [],
        }

    product_rows = (
        db.session.query(Product.id, Product.reference)
        .filter(Product.campaign_id == active_campaign_id())
        .filter(Product.id.in_(aggregates.keys()))
        .all()
    )

    scored_rows = []
    max_votes = 0
    max_qty = 0.0
    max_cost_log = 0.0

    for row in product_rows:
        totals = aggregates.get(row.id, {})
        votes = int(totals.get("num_votes", 0) or 0)
        qty_total = float(totals.get("total_quantity", 0) or 0)
        amount_total = float(totals.get("total_amount", 0) or 0)
        cost_per_piece = (amount_total / qty_total) if qty_total else 0.0
        cost_log = math.log1p(cost_per_piece)

        max_votes = max(max_votes, votes)
        max_qty = max(max_qty, qty_total)
        max_cost_log = max(max_cost_log, cost_log)

        scored_rows.append(
            {
                "id": row.id,
                "reference": row.reference or "",
                "votes": votes,
                "qty_total": qty_total,
                "amount_total": amount_total,
                "cost_log": cost_log,
            }
        )

    max_votes = max_votes or 1
    max_qty = max_qty or 1.0
    max_cost_log = max_cost_log or 1.0

    for row in scored_rows:
        votes_norm = row["votes"] / max_votes
        qty_norm = row["qty_total"] / max_qty
        cost_norm = row["cost_log"] / max_cost_log
        row["score"] = 0.40 * votes_norm + 0.35 * qty_norm + 0.25 * cost_norm

    scored_rows.sort(
        key=lambda row: (
            -row["score"],
            -row["votes"],
            -row["amount_total"],
            row["reference"],
        )
    )

    remaining_slots = max(limit - len(locked_ids), 0)
    selected_voted_ids = [
        row["id"] for row in scored_rows if row["id"] not in locked_ids
    ][:remaining_slots]
    selected_ids = set(locked_ids) | set(selected_voted_ids)

    return {
        "limit": limit,
        "locked_ids": locked_ids,
        "selected_ids": selected_ids,
        "selected_voted_ids": selected_voted_ids,
        "ranked_ids": [row["id"] for row in scored_rows],
    }
