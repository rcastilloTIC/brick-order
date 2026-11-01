"""Idempotent bulk transfer of selected voting commitments to order rows.

Rejected votes remain untouched; only selected products in the active campaign
are materialized. Existing order quantities are never reduced.
"""
from collections import defaultdict

from app import db
from app.models import Order, Product, UserVote
from app.services.campaign_data import active_campaign_id


def missing_order_floors(votes, orders, selected_ids):
    """Pure planner: return {(user_id, product_id): missing_quantity}."""
    try:
        selected = set(selected_ids)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid selected references") from exc
    if any(type(product_id) is not int or product_id <= 0 for product_id in selected):
        raise ValueError("Invalid selected reference identifier")
    voted = defaultdict(int)
    ordered = defaultdict(int)
    for user_id, product_id, quantity in votes:
        if type(user_id) is not int or user_id <= 0 or type(product_id) is not int or product_id <= 0:
            raise ValueError("Invalid voting identity")
        if product_id in selected:
            if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity <= 0:
                raise ValueError("Invalid voting commitment")
            voted[(user_id, product_id)] += quantity
    for user_id, product_id, quantity in orders:
        if type(user_id) is not int or user_id <= 0 or type(product_id) is not int or product_id <= 0:
            raise ValueError("Invalid order identity")
        if product_id in selected:
            if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity <= 0:
                raise ValueError("Invalid order quantity")
            ordered[(user_id, product_id)] += quantity
    return {key: quantity - ordered[key] for key, quantity in voted.items()
            if quantity > ordered[key]}


def materialize_selected_commitments():
    """Persist only the missing vote floor, in the current campaign.

    Call at the controlled final -> order transition, after final selection
    has been computed. The caller owns the transaction and commits on success.
    Returns (new_order_rows, added_units).
    """
    campaign_id = active_campaign_id()
    selected = {pid for (pid,) in db.session.query(Product.id).filter(
        Product.campaign_id == campaign_id, Product.final_selected.is_(True),
        Product.final_disabled.is_(False)).all()}
    if not selected:
        raise ValueError("No hay referencias seleccionadas para generar pedidos.")
    votes = db.session.query(UserVote.user_id, UserVote.product_id, UserVote.quantity).filter(
        UserVote.campaign_id == campaign_id, UserVote.product_id.in_(selected)).all()
    orders = db.session.query(Order.user_id, Order.product_id, Order.quantity).filter(
        Order.campaign_id == campaign_id, Order.product_id.in_(selected)).all()
    missing = missing_order_floors(votes, orders, selected)
    for (user_id, product_id), quantity in sorted(missing.items()):
        db.session.add(Order(campaign_id=campaign_id, user_id=user_id,
                             product_id=product_id, quantity=quantity))
    db.session.flush()
    return len(missing), sum(missing.values())


def assert_selected_commitments_materialized():
    """Fail closed if any selected vote floor is absent from persisted orders.

    Must run in the same transaction/snapshot as the final export. Historical
    votes for discarded products are intentionally excluded.
    """
    campaign_id = active_campaign_id()
    selected = {pid for (pid,) in db.session.query(Product.id).filter(
        Product.campaign_id == campaign_id,
        Product.final_selected.is_(True),
        Product.final_disabled.is_(False),
    ).all()}
    if not selected:
        raise ValueError("No hay referencias seleccionadas para exportar.")
    votes = db.session.query(
        UserVote.user_id, UserVote.product_id, UserVote.quantity
    ).filter(UserVote.campaign_id == campaign_id,
             UserVote.product_id.in_(selected)).all()
    orders = db.session.query(
        Order.user_id, Order.product_id, Order.quantity
    ).filter(Order.campaign_id == campaign_id,
             Order.product_id.in_(selected)).all()
    missing = missing_order_floors(votes, orders, selected)
    if missing:
        raise ValueError(
            "Hay compromisos seleccionados sin trasladar a pedidos "
            f"({len(missing)} participante/referencia). "
            "Complete la materializacion antes de exportar."
        )
