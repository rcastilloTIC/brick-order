"""V85 public shortage resolution. Campaign-scoped, idempotent, no automatic cancellation without a worker.

A shortage is measured from stored orders, NOT raw voting totals. This workflow is
kept out of Extended, which retains its private extension system.
"""
from datetime import datetime, timedelta
from decimal import Decimal
from sqlalchemy import func
from app import db
from app.models import CampaignParticipation, Order, Product, ShortageWindow, ShortageAcknowledgement, ActionLog
from app.services.active_campaign import current_campaign
from app.services.campaign_phase import get_campaign_phase
from app.services.campaign_settings import get_annual_setting
from app.services.mode import get_limit_configuration


def order_total(campaign_id):
    rows = db.session.query(Order.quantity, Product.price).join(Product, Product.id == Order.product_id).filter(
        Order.campaign_id == campaign_id, Product.campaign_id == campaign_id).all()
    return sum((Decimal(q) * Decimal(str(price or 0)) for q, price in rows), Decimal('0'))


def minimum_total():
    from flask import current_app
    value = get_annual_setting('limit_minimum_total')
    return Decimal(str(value if value is not None else current_app.config.get('MIN_TOTAL_ORDER_AMOUNT', 4800)))


def personal_total(campaign_id, user_id):
    rows = db.session.query(Order.quantity, Product.price).join(Product, Product.id == Order.product_id).filter(
        Order.campaign_id == campaign_id, Product.campaign_id == campaign_id, Order.user_id == user_id).all()
    return sum((Decimal(q) * Decimal(str(price or 0)) for q, price in rows), Decimal('0'))


def user_margin(campaign_id, user_id):
    """Conservative margin including selected voting floors not yet materialized."""
    from app.models import UserVote
    from app.services.commitment_ledger import effective_commitment
    if not current_campaign() or current_campaign().id != campaign_id:
        raise ValueError('Campana no activa')
    ceiling = Decimal(str(get_limit_configuration()['phase_one_order_limit']))
    orders = Order.query.filter_by(campaign_id=campaign_id, user_id=user_id).all()
    votes = UserVote.query.filter_by(campaign_id=campaign_id, user_id=user_id).all()
    selected = {p.id for p in Product.query.filter_by(campaign_id=campaign_id, final_selected=True).all()}
    committed = effective_commitment(
        [(o.product_id, o.product.price, o.quantity) for o in orders],
        [(v.product_id, v.product.price, v.quantity) for v in votes],
        phase='order', selected_product_ids=selected)
    return max(Decimal('0'), ceiling - committed)


def window_for_active():
    campaign = current_campaign()
    return ShortageWindow.query.filter_by(campaign_id=campaign.id).one_or_none() if campaign else None


def open_window(actor_id, days, now=None):
    now = now or datetime.utcnow()
    if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= 30:
        raise ValueError('El plazo debe ser de 1 a 30 dias')
    campaign = current_campaign()
    if campaign is None or get_campaign_phase() != 'order':
        raise ValueError('Solo disponible durante la fase de pedido')
    if window_for_active():
        raise ValueError('Ya se ha tomado una decision para esta campana')
    if order_total(campaign.id) >= minimum_total():
        raise ValueError('El pedido ya alcanza el minimo')
    row = ShortageWindow(campaign_id=campaign.id, status='open', opened_by=actor_id,
                         opened_at=now, deadline_at=now + timedelta(days=days))
    db.session.add(row)
    db.session.add(ActionLog(user_id=actor_id, action='shortage_open', detail=f'campaign={campaign.id};days={days}'))
    db.session.commit()
    return row


def acknowledge(user_id, now=None):
    row = window_for_active()
    campaign = current_campaign()
    if row is None or row.status != 'open' or (row.deadline_at and (now or datetime.utcnow()) >= row.deadline_at):
        raise ValueError('No hay aviso activo')
    membership = CampaignParticipation.query.filter_by(campaign_id=campaign.id,user_id=user_id).one_or_none()
    if membership is None or membership.status != 'approved' or not membership.signed_document:
        raise ValueError('No participa en la campana')
    existing = ShortageAcknowledgement.query.filter_by(window_id=row.id,user_id=user_id).first()
    if existing:return existing
    accepted = ShortageAcknowledgement(window_id=row.id,user_id=user_id,accepted_at=now or datetime.utcnow())
    db.session.add(accepted)
    db.session.commit()
    return accepted


def reconcile(now=None):
    """Idempotent worker. A reached minimum wins even at the deadline."""
    now = now or datetime.utcnow()
    row = window_for_active()
    if row is None or row.status != 'open':return None
    total = order_total(row.campaign_id)
    if total >= minimum_total():
        row.status = 'reached'; row.closing_reason = 'minimum_reached'
    elif now >= row.deadline_at:
        row.status = 'cancelled'; row.closing_reason = 'deadline_expired'
    else:return row.status
    row.resolved_at = now
    db.session.add(ActionLog(user_id=row.opened_by,action='shortage_close',
                             detail=f'campaign={row.campaign_id};status={row.status}'))
    db.session.commit()
    return row.status


def cancel(actor_id, now=None):
    row = window_for_active()
    campaign = current_campaign()
    if campaign is None or get_campaign_phase() != 'order':
        raise ValueError('No hay pedido activo para cancelar')
    if row and row.status != 'open':
        raise ValueError('Decision ya cerrada')
    if row is None:
        if order_total(campaign.id) >= minimum_total():
            raise ValueError('No se permite cancelar por insuficiencia un pedido que cumple el minimo')
        row = ShortageWindow(campaign_id=campaign.id,opened_by=actor_id,opened_at=now or datetime.utcnow())
        db.session.add(row)
    row.status='cancelled';row.closing_reason='admin_cancelled';row.resolved_at=now or datetime.utcnow()
    db.session.add(ActionLog(user_id=actor_id,action='shortage_close',detail=f'campaign={campaign.id};status=cancelled'))
    db.session.commit()
    return row


def selected_products_for_extension(campaign_id):
    """Only selected, enabled products in the current annual catalogue."""
    return Product.query.filter_by(campaign_id=campaign_id, final_selected=True, final_disabled=False).order_by(Product.reference).all()


def _add_extra_order_locked(user_id, product_id, quantity, now=None):
    """Additive participant order during the acknowledged extraordinary window.

    Fail closed on deadline, cancelled state, unsigned membership, unselected
    products, invalid price/quantity, materialization and campaign limits.
    """
    from app.models import UserVote, Config
    from app.services.commitment_ledger import effective_commitment, materialized_order_quantity
    from app.services.quantity_rules import validate_quantity
    now = now or datetime.utcnow()
    # Serialize competing read-check-write transactions across Gunicorn workers.
    # This app uses SQLite; BEGIN IMMEDIATE takes a RESERVED write lock before
    # reading the financial ledger. SQLite waits for the competing transaction
    # according to its busy timeout, rather than allowing both to validate.
    from sqlalchemy import text
    connection = db.session.connection()
    if connection.dialect.name != 'sqlite':
        raise RuntimeError('Extraordinary increases require SQLite serialization')
    connection.exec_driver_sql('BEGIN IMMEDIATE')
    row = window_for_active()
    campaign = current_campaign()
    if not row or row.status != 'open' or not campaign or campaign.id != row.campaign_id:
        raise ValueError('No hay ampliacion publica abierta')
    if get_campaign_phase() != 'order' or not row.deadline_at or now >= row.deadline_at:
        raise ValueError('El plazo extraordinario ha finalizado')
    if order_total(campaign.id) >= minimum_total():
        raise ValueError('Ya se ha alcanzado el minimo colectivo')
    if Config.get('final_order_generated_at'):
        raise ValueError('El pedido definitivo ya esta cerrado')
    membership = CampaignParticipation.query.filter_by(campaign_id=campaign.id, user_id=user_id).one_or_none()
    if not membership or membership.status != 'approved' or not membership.signed_document:
        raise ValueError('Participante no autorizado')
    if not ShortageAcknowledgement.query.filter_by(window_id=row.id, user_id=user_id).first():
        raise ValueError('Debe aceptar el aviso antes de ampliar')
    if not isinstance(product_id, int) or isinstance(product_id, bool) or not isinstance(quantity, int) or isinstance(quantity, bool):
        raise ValueError('Datos de pedido no validos')
    product = Product.query.filter_by(id=product_id, campaign_id=campaign.id, final_selected=True, final_disabled=False).first()
    if not product:
        raise ValueError('Referencia no seleccionada o fuera de campana')
    valid, reason = validate_quantity(product.price, quantity)
    if not valid:
        raise ValueError(reason)
    limit = Decimal(str(get_limit_configuration()['phase_one_order_limit']))
    if not limit.is_finite() or limit <= 0:
        raise ValueError('Limite individual invalido')
    orders = db.session.query(Order).filter_by(campaign_id=campaign.id, user_id=user_id).all()
    votes = db.session.query(UserVote).filter_by(campaign_id=campaign.id, user_id=user_id).all()
    order_lines = [(o.product_id, o.product.price, o.quantity) for o in orders]
    vote_lines = [(v.product_id, v.product.price, v.quantity) for v in votes]
    selected_ids = {p.id for p in selected_products_for_extension(campaign.id)}
    try:
        projected = effective_commitment(order_lines, vote_lines, phase='order',
            selected_product_ids=selected_ids, additional=(product.id, Decimal(str(product.price)), quantity))
        if projected > limit:
            raise ValueError('Se supera el limite individual de la campana')
        stored = materialized_order_quantity(order_lines, vote_lines,
            product_id=product.id, additional_quantity=quantity)
    except (TypeError, ArithmeticError, AttributeError) as exc:
        raise ValueError('No se puede validar el compromiso') from exc
    entry = Order(campaign_id=campaign.id, user_id=user_id, product_id=product.id, quantity=stored)
    db.session.add(entry)
    db.session.add(ActionLog(user_id=user_id, action='shortage_order_increase',
        detail=f'campaign={campaign.id};product={product.id};extra={quantity};stored={stored}'))
    db.session.commit()
    return entry


def add_extra_order(user_id, product_id, quantity, now=None):
    """Atomic read-check-write boundary; roll back reserved locks on failure."""
    try:
        return _add_extra_order_locked(user_id, product_id, quantity, now)
    except BaseException:
        db.session.rollback()
        raise
