from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.orm import joinedload

from app import db
from app.models import CampaignParticipation, Config, Order, Product, User, UserVote
from app.services.campaign_data import active_campaign_id, orders_query, products_query
from app.services.active_campaign import require_campaign_participant
from app.services.quantity_rules import validate_quantity
from app.services.commitment_ledger import effective_commitment, materialized_order_quantity
from app.services.mode import get_limit_configuration
from decimal import Decimal, InvalidOperation

orders_bp = Blueprint("orders", __name__, template_folder="templates/orders")


@orders_bp.route("/", methods=["GET"])
@login_required
def list_orders():
    _ensure_admin()
    orders = (
        orders_query().options(joinedload(Order.product), joinedload(Order.user))
        .order_by(Order.timestamp.desc())
        .all()
    )
    return render_template("orders/list.html", orders=orders)


@orders_bp.route("/create", methods=["GET", "POST"])
@login_required
def create_order():
    """Admin-only order entry, always assigned to an approved campaign member.

    The previous implementation assigned new orders to the administrator's own
    account and accepted arbitrary quantities. Fail closed when the final order
    has already been generated, or when a quantity/limit cannot be validated.
    """
    _ensure_admin()
    campaign_id = active_campaign_id()
    if Config.get("final_order_generated_at"):
        abort(409, description="El pedido definitivo está cerrado.")
    products = products_query().order_by(Product.name.asc(), Product.reference.asc()).all()
    eligible = (db.session.query(User)
        .join(CampaignParticipation, CampaignParticipation.user_id == User.id)
        .filter(CampaignParticipation.campaign_id == campaign_id,
                CampaignParticipation.status == 'approved',
                CampaignParticipation.signed_document.isnot(None),
                User.is_admin.is_(False))
        .order_by(User.username.asc()).all())
    if request.method == "POST":
        product_id = request.form.get("product_id", type=int)
        target_user_id = request.form.get("user_id", type=int)
        quantity = request.form.get("quantity", type=int)
        product = products_query().filter_by(id=product_id).first() if product_id else None
        if not product or not target_user_id or quantity is None:
            abort(400, description="Producto, participante y cantidad son obligatorios.")
        require_campaign_participant(target_user_id)
        valid, reason = validate_quantity(product.price, quantity)
        if not valid:
            abort(400, description=reason)
        try:
            limit = Decimal(str(get_limit_configuration()["phase_one_order_limit"]))
            price = Decimal(str(product.price))
            if not limit.is_finite() or limit <= 0 or not price.is_finite() or price < 0:
                raise ValueError("Invalid monetary configuration")
            # A per-product union is essential: max(grand totals) would undercount
            # disjoint references across the two legacy storage mechanisms.
            current_orders = [(o.product_id, o.product.price, o.quantity)
                for o in orders_query().filter_by(user_id=target_user_id).all()]
            current_votes = [(v.product_id, v.product.price, v.quantity)
                for v in UserVote.query.filter_by(campaign_id=campaign_id,
                    user_id=target_user_id).all()]
            phase = Config.get("phase") or "first"
            selected_ids = None
            if phase not in {'first', 'second'}:
                selected_ids = {p.id for p in products_query().filter(
                    Product.final_selected.is_(True)).with_entities(Product.id).all()}
            projected = effective_commitment(current_orders, current_votes,
                phase=phase, selected_product_ids=selected_ids,
                additional=(product.id, price, quantity))
            if projected > limit:
                abort(400, description="Se supera el límite económico de la campaña.")
            # During ordering, persist the selected voting floor as actual
            # order quantity on first conversion; an unselected vote is never
            # converted. The ledger already incorporates this floor in projected.
            stored_quantity = quantity if selected_ids is None else materialized_order_quantity(
                current_orders, current_votes, product_id=product.id,
                additional_quantity=quantity)
        except (InvalidOperation, ValueError, TypeError, AttributeError):
            abort(409, description="No es posible validar el límite económico.")
        order = Order(product=product, quantity=stored_quantity, user_id=target_user_id,
                      campaign_id=campaign_id)
        db.session.add(order)
        db.session.commit()
        flash("Pedido creado correctamente.", "success")
        return redirect(url_for("orders.list_orders"))
    return render_template("orders/create.html", products=products, participants=eligible)


def _ensure_admin() -> None:
    if not current_user.is_authenticated or not current_user.is_admin:
        abort(403)
