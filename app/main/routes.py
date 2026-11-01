from __future__ import annotations
from app.services.campaign_settings import ANNUAL_KEYS, get_annual_setting, set_annual_setting
from app.services.campaign_phase import get_campaign_phase, set_campaign_phase

import csv
import io
import os
import re
import tempfile
import threading
import zipfile
from datetime import date, datetime
from typing import Dict, Tuple, List, Set

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    send_file,
    session,
    url_for,
)
from flask_login import current_user, login_required

from sqlalchemy import case, func, or_
from sqlalchemy.exc import SQLAlchemyError
from openpyxl import load_workbook

from app import db
from app.models import (
    Config,
    Order,
    Product,
    User,
    UserVote,
    ActionLog,
    ColorMap,
    UserFavorite,
)
from app.services.final_selection import (
    compute_final_selection,
    get_final_selection_snapshot,
    get_vote_aggregates,
    get_phase_two_selection_snapshot,
    get_neutral_ranking,
)
from app.services.order_exports import (
    build_final_order_context,
    generate_order_files,
)
from app.services.mode import (
    TEST_MODE_KEY,
    get_limit_configuration,
    is_test_mode_enabled,
)
from app.services.declarations import (
    clear_declaration_issue,
    remove_declaration_file,
    set_declaration_issue,
)
from app.services.backups import (
    RestoreError,
    create_phase_backup,
    restore_backup,
    write_backup_error_log,
)
from app.services.activity_log import ACTION_LABELS, log_user_action
from app.i18n import is_safe_local_url, set_current_language
from app.services.active_campaign import current_campaign, require_campaign_participant
from app.services.commitment_ledger import effective_commitment, committed_total
from decimal import Decimal
from app.services.campaign_data import (
    active_campaign_id, products_query, orders_query, votes_query, favorites_query, validate_product_campaign,
)

main_bp = Blueprint("main", __name__)

PHASES = ("first", "second", "final", "order")
DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 200

FINAL_ORDER_MIN_TOTAL = 4800


@main_bp.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("main.user_dashboard"))
    return redirect(url_for("auth.login"))


@main_bp.route("/language/<string:lang>", methods=["GET"], endpoint="set_language")
def set_language(lang: str):
    if not set_current_language(lang):
        abort(404)
    next_url = request.args.get("next")
    if is_safe_local_url(next_url):
        return redirect(next_url)
    if current_user.is_authenticated:
        return redirect(url_for("main.user_dashboard"))
    return redirect(url_for("auth.login"))


@main_bp.route("/dashboard", methods=["GET"], endpoint="user_dashboard")
@login_required
def user_dashboard():
    if not current_user.is_admin:
        require_campaign_participant(current_user.id)
    filters = _parse_product_filters()
    page = max(request.args.get("page", 1, type=int), 1)
    per_page = request.args.get("per_page", DEFAULT_PAGE_SIZE, type=int)
    per_page = min(max(per_page, 1), MAX_PAGE_SIZE)
    phase = get_current_phase()
    test_mode = is_test_mode_enabled()
    active_limits = get_limit_configuration(test_mode=test_mode)

    base_query = products_query()
    if phase in {"final", "order"}:
        base_query = base_query.filter(Product.final_selected.is_(True))
        base_query = base_query.filter(Product.final_disabled.is_(False))
    elif phase == "second":
        visible_ids = _get_products_with_votes_or_locked()
        if visible_ids:
            base_query = base_query.filter(Product.id.in_(visible_ids))
        else:
            base_query = base_query.filter(Product.id.is_(None))

    ranking_context = (
        get_neutral_ranking(limit=active_limits["final_selection_limit"])
        if phase in {"final", "order"}
        else None
    )

    order_mode = request.args.get("order_mode", "ranking").strip() or "ranking"
    if order_mode not in {"ranking", "mine"}:
        order_mode = "ranking"

    query = _apply_product_filters(base_query, filters)
    if filters["votes_only"] == "1":
        query = query.filter(or_(Product.is_locked.is_(True), Product.id.in_(_get_products_with_votes())))

    user_vote_exists = (
        db.session.query(UserVote.id)
        .filter(UserVote.user_id == current_user.id, UserVote.product_id == Product.id, UserVote.campaign_id == active_campaign_id())
        .exists()
    )
    has_any_votes = (
        db.session.query(UserVote.id)
        .filter(UserVote.product_id == Product.id, UserVote.campaign_id == active_campaign_id())
        .exists()
    )
    locked_first = case((Product.is_locked.is_(True), 0), else_=1)
    voted_first = case((user_vote_exists, 0), else_=1)
    ranking_ids = None
    if phase in {"order"} and ranking_context:
        ranking_ids = [row["id"] for row in ranking_context["rows"]]
        if ranking_ids:
            rank_map = {pid: idx for idx, pid in enumerate(ranking_ids)}
            rank_case = case(rank_map, value=Product.id, else_=len(ranking_ids) + 1000)
            if order_mode == "mine":
                locked_last = case((Product.is_locked.is_(True), 1), else_=0)
                query = query.order_by(locked_last, voted_first, rank_case, Product.id.asc())
            else:
                query = query.order_by(rank_case, Product.id.asc())

    if ranking_ids:
        pass
    elif filters["price_order"] == "asc":
        query = query.order_by(locked_first, voted_first, Product.price.asc(), Product.id.asc())
    elif filters["price_order"] == "desc":
        query = query.order_by(locked_first, voted_first, Product.price.desc(), Product.id.asc())
    else:
        query = query.order_by(locked_first, voted_first, Product.id.asc())

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    favorite_ids = {
        row.product_id
        for row in favorites_query().filter_by(user_id=current_user.id).all()
    }
    if favorite_ids:
        favorite_query = base_query.filter(Product.id.in_(favorite_ids))
    else:
        favorite_query = base_query.filter(Product.id.is_(None))
    if filters["price_order"] == "asc":
        favorite_query = favorite_query.order_by(
            locked_first, voted_first, Product.price.asc(), Product.id.asc()
        )
    elif filters["price_order"] == "desc":
        favorite_query = favorite_query.order_by(
            locked_first, voted_first, Product.price.desc(), Product.id.asc()
        )
    else:
        favorite_query = favorite_query.order_by(locked_first, voted_first, Product.id.asc())
    favorite_products = favorite_query.all()
    aggregates = get_vote_aggregates()
    user_votes, total_order = _collect_user_votes(current_user.id)
    if phase in {"order", "final"}:
        filtered_votes = {}
        filtered_total = 0.0
        for product_id, entry in user_votes.items():
            if entry.get("final_disabled") or not entry.get("final_selected"):
                continue
            filtered_votes[product_id] = entry
            filtered_total += (entry["vote"].quantity or 0) * float(entry["price"] or 0)
        user_votes = filtered_votes
        total_order = filtered_total

    # Display the actual budget after cutoff: rejected votes are retained for
    # audit but cease to consume purchasing power once selection is confirmed.
    # Use the same ledger as administrative order creation; do not calculate
    # available funds by simply summing all historical votes.
    campaign_orders = orders_query().filter_by(user_id=current_user.id).all()
    order_lines = [(row.product_id, row.product.price, row.quantity) for row in campaign_orders]
    vote_lines = [(pid, entry["price"], entry["vote"].quantity)
                  for pid, entry in user_votes.items()]
    # user_votes is filtered below the selection in the original flow. For
    # released-budget reporting, recover historical votes separately.
    historical_votes = votes_query().filter_by(user_id=current_user.id).all()
    historical_lines = [(row.product_id, row.product.price, row.quantity)
                        for row in historical_votes]
    selected_ids_for_budget = None
    if phase in {"final", "order"}:
        selected_ids_for_budget = {pid for pid, in products_query().filter(
            Product.final_selected.is_(True), Product.final_disabled.is_(False)
        ).with_entities(Product.id).all()}
    try:
        active_commitment = effective_commitment(
            order_lines, historical_lines, phase=phase,
            selected_product_ids=selected_ids_for_budget)
        previously_committed = committed_total([], historical_lines)
        budget_limit = Decimal(str(active_limits["phase_one_order_limit"]))
        if not budget_limit.is_finite() or budget_limit <= 0:
            raise ValueError("Invalid campaign budget")
        available_budget = max(Decimal("0"), budget_limit - active_commitment)
        released_budget = (max(Decimal("0"), previously_committed -
                           committed_total([], [line for line in historical_lines
                               if selected_ids_for_budget is None or line[0] in selected_ids_for_budget]))
                           if selected_ids_for_budget is not None else Decimal("0"))
    except (ValueError, TypeError, AttributeError):
        abort(409, description="No se puede calcular el presupuesto de esta campaña.")

    voting_open = phase not in {"final"}
    phase2_selection = None
    phase2_selected_ids: Set[int] = set()
    phase2_selected_voted_ids: Set[int] = set()
    if phase == "second":
        phase2_selection = get_phase_two_selection_snapshot(
            limit=active_limits["final_selection_limit"]
        )
        phase2_selected_ids = set(phase2_selection["selected_ids"])
        phase2_selected_voted_ids = set(phase2_selection["selected_voted_ids"])
    main_group_tops = _get_distinct_main_group_tops()
    main_groups = _get_distinct_main_groups()
    main_group_subs = _get_distinct_main_group_subs()
    colour_options = _get_distinct_colours()
    colour_label_map = {option["value"]: option["label"] for option in colour_options}
    colour_filter_label = colour_label_map.get(filters["colour"], filters["colour"])

    order_generated_at_raw = get_annual_setting('final_order_generated_at')
    order_generated_at_display = _format_timestamp(order_generated_at_raw)
    applied_tax = _get_config_float("final_order_last_tax")
    applied_shipping = _get_config_float("final_order_last_shipping")
    final_order_summary = None
    final_order_user = None
    final_order_extra = 0.0
    total_order_display = total_order
    if phase in {"order", "final"} and order_generated_at_raw:
        final_order_summary = build_final_order_context()
        final_order_user = final_order_summary.get("participants", {}).get(current_user.id)
        base_total_amount = float(final_order_summary.get("base_total", 0.0) or 0.0)
        extras_total = applied_tax + applied_shipping
        if final_order_user and base_total_amount > 0:
            user_subtotal = float(final_order_user.get("subtotal", 0.0) or 0.0)
            final_order_extra = extras_total * (user_subtotal / base_total_amount)
            total_order_display = user_subtotal + final_order_extra

    from app.services import shortage as shortage_service
    from app.models import ShortageAcknowledgement
    shortage_notice=shortage_service.window_for_active()
    shortage_acknowledged=False
    shortage_margin=Decimal('0')
    if shortage_notice and not current_user.is_admin:
        shortage_acknowledged=ShortageAcknowledgement.query.filter_by(
            window_id=shortage_notice.id,user_id=current_user.id).first() is not None
        shortage_margin=shortage_service.user_margin(shortage_notice.campaign_id,current_user.id)
    return render_template(
        "user_dashboard.html",
        products=pagination.items,
        pagination=pagination,
        favorite_products=favorite_products,
        favorite_ids=favorite_ids,
        aggregates=aggregates,
        user_votes=user_votes,
        total_order=total_order,
        total_order_display=total_order_display,
        active_commitment=active_commitment,
        available_budget=available_budget,
        released_budget=released_budget,
        voting_open=voting_open,
        phase2_selected_ids=phase2_selected_ids,
        phase2_selected_voted_ids=phase2_selected_voted_ids,
        current_phase=phase,
        order_mode=order_mode,
        per_page=per_page,
        **_template_filter_context(filters),
        main_group_top_options=main_group_tops,
        main_group_options=main_groups,
        main_group_sub_options=main_group_subs,
        colour_options=colour_options,
        colour_filter_label=colour_filter_label,
        active_limits=active_limits,
        test_mode_enabled=test_mode,
        final_order_summary=final_order_summary,
        final_order_user=final_order_user,
        final_order_extra=final_order_extra,
        order_generated_at=order_generated_at_display,
        user_order_pdf_available=bool(get_annual_setting('final_order_user_pdf')) and final_order_user is not None,
        ranking_context=ranking_context,
        applied_tax=applied_tax,
        applied_shipping=applied_shipping,
        min_total=float(get_annual_setting('limit_minimum_total') or current_app.config.get("MIN_TOTAL_ORDER_AMOUNT", FINAL_ORDER_MIN_TOTAL)),
            shortage_notice=shortage_notice, shortage_acknowledged=shortage_acknowledged, shortage_margin=shortage_margin,
    )


@main_bp.route("/vote", methods=["POST"], endpoint="vote")
@login_required
def submit_vote():
    phase = get_current_phase()
    if phase not in {"first", "second", "order"}:
        abort(409, description="La fase actual no permite registrar votos.")
    if _order_is_finalized():
        abort(409, description='El pedido ya está cerrado.')
    active_limits = get_limit_configuration()
    log_user_action(
        current_user.id,
        "vote_attempt",
        detail=f"Intento de voto (fase={phase})",
    )
    product_id = request.form.get("product_id", type=int)
    quantity = request.form.get("quantity", type=int)

    if not product_id or quantity is None or quantity <= 0:
        flash("Debes indicar una cantidad válida para votar.", "warning")
        return _dashboard_redirect()

    require_campaign_participant(current_user.id)
    product = products_query().filter_by(id=product_id).first_or_404()
    if phase == "order" and not product.final_selected:
        flash("Solo puedes pedir referencias seleccionadas en la fase de pedido.", "warning")
        return _dashboard_redirect()
    if product.price is None or product.price <= 0:
        flash("Esta referencia no tiene precio asignado y no se puede pedir.", "warning")
        return _dashboard_redirect()
    is_valid, message = _validate_quantity_for_product(product.price, quantity)
    if not is_valid:
        flash(message, "warning")
        return _dashboard_redirect()
    vote = votes_query().filter_by(user_id=current_user.id, product_id=product_id).first()
    previous_quantity = vote.quantity if vote else 0
    # A registered vote is a binding purchase commitment. No phase permits
    # lowering or deleting it, including expansion rounds and admin edits.
    from app.services.vote_commitments import assert_nondecreasing_vote
    assert_nondecreasing_vote(previous_quantity, quantity)

    if phase in {"first", "second"}:
        base_total = _calculate_user_total(current_user.id)
        new_total = base_total - previous_quantity * product.price + quantity * product.price
        limit_amount = active_limits["phase_one_order_limit"]
        if new_total > limit_amount:
            flash(f"Has superado el límite de {limit_amount:.2f}€.", "danger")
            return _dashboard_redirect()

        if phase == "first":
            max_refs = active_limits["max_refs_phase_one"]
        else:
            max_refs = active_limits["max_refs_phase_two"]

        distinct_refs = (
            db.session.query(UserVote.product_id)
            .filter(UserVote.user_id == current_user.id, UserVote.campaign_id == active_campaign_id())
            .distinct()
            .count()
        )

        if not vote and distinct_refs >= max_refs:
            flash(f"Solo puedes seleccionar un máximo de {max_refs} referencias en esta fase.", "danger")
            return _dashboard_redirect()
    elif phase == "order":
        base_total = _calculate_user_total_final_selected(current_user.id)
        new_total = base_total - previous_quantity * product.price + quantity * product.price
        limit_amount = active_limits["phase_one_order_limit"]
        if new_total > limit_amount:
            flash(f"Has superado el límite de {limit_amount:.2f}€.", "danger")
            return _dashboard_redirect()


    if vote:
        if phase == "first":
            vote.initial_quantity = quantity
        if phase == "second" and vote.phase == "first":
            if vote.initial_quantity is None:
                vote.initial_quantity = previous_quantity
            if quantity < (vote.initial_quantity or 0):
                flash("No puedes reducir la cantidad por debajo de la votada en fase 1.", "danger")
                return _dashboard_redirect()
        vote.quantity = quantity
        if vote.phase != "first":
            vote.phase = phase
        product_label = f"{product.reference} - {product.name}" if product.name else product.reference
        log_user_action(
            current_user.id,
            "vote_updated",
            detail=f"{product_label}: {previous_quantity} -> {quantity}",
        )
    else:
        vote = UserVote(
            campaign_id=active_campaign_id(),
            user_id=current_user.id,
            product_id=product_id,
            quantity=quantity,
            initial_quantity=quantity if phase == "first" else None,
            phase=phase,
        )
        db.session.add(vote)
        product_label = f"{product.reference} - {product.name}" if product.name else product.reference
        log_user_action(
            current_user.id,
            "vote_added",
            detail=f"{product_label}: {quantity} uds",
        )

    db.session.commit()
    flash(f"Voto registrado para {product.reference}.", "success")
    return _dashboard_redirect()


@main_bp.route("/favorite", methods=["POST"], endpoint="toggle_favorite")
@login_required
def toggle_favorite():
    require_campaign_participant(current_user.id)
    if _order_is_finalized():
        abort(409, description="La campaña está cerrada.")
    product_id = request.form.get("product_id", type=int)
    if not product_id:
        flash("No se pudo identificar la referencia.", "warning")
        return _dashboard_redirect()
    products_query().filter_by(id=product_id).first_or_404()
    favorite = favorites_query().filter_by(
        user_id=current_user.id, product_id=product_id
    ).first()
    if favorite:
        db.session.delete(favorite)
        flash("Favorita eliminada.", "info")
    else:
        db.session.add(UserFavorite(campaign_id=active_campaign_id(), user_id=current_user.id, product_id=product_id))
        flash("Referencia marcada como favorita.", "success")
    db.session.commit()
    return _dashboard_redirect()


@main_bp.route("/vote/delete", methods=["POST"], endpoint="delete_vote")
@login_required
def delete_vote():
    if get_current_phase() in {"final"}:
        flash("La fase final no permite modificar votos.", "warning")
        return _dashboard_redirect()

    product_id = request.form.get("product_id", type=int)
    if not product_id:
        flash("Referencia no válida para borrar el voto.", "warning")
        return _dashboard_redirect()

    require_campaign_participant(current_user.id)
    # Keep the endpoint for old pages, but never delete binding commitments.
    flash("Los votos comprometidos no se pueden eliminar ni reducir.", "danger")
    return _dashboard_redirect()






@main_bp.route("/dashboard/order-pdf", methods=["GET"], endpoint="download_user_order_pdf")
@login_required
def download_user_order_pdf():
    require_campaign_participant(current_user.id)
    zip_name = get_annual_setting('final_order_user_pdf')
    if not zip_name:
        abort(404)
    from app.services.export_path_safety import safe_export_path
    folder = current_app.config["ORDER_EXPORT_FOLDER"]
    zip_path = safe_export_path(folder, zip_name, suffix=".zip")
    if zip_path is None:
        abort(404)

    archive_name = f"{_safe_archive_name(current_user.username)}.pdf"
    try:
        with zipfile.ZipFile(zip_path, "r") as archive:
            try:
                data = archive.read(archive_name)
            except KeyError:
                abort(404)
    except zipfile.BadZipFile:
        abort(404)

    return send_file(
        io.BytesIO(data),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"pedido_{current_user.username}.pdf",
    )


@main_bp.route("/admin/campaign-archive", methods=["POST"], endpoint="campaign_archive")
@login_required
def campaign_archive():
    """Archive a finished campaign without touching its historical records."""
    _ensure_admin()
    from app.services.campaign_archive import archive_completed_campaign, CampaignArchiveError
    try:
        submitted_year = int(request.form.get('confirm_year', ''))
    except (TypeError, ValueError):
        abort(400, description='Confirma el año numérico de la campaña.')
    try:
        archive_completed_campaign(year=submitted_year,
            export_folder=current_app.config['ORDER_EXPORT_FOLDER'],
            actor_id=current_user.id)
    except CampaignArchiveError as exc:
        db.session.rollback()
        flash(str(exc), 'danger')
    else:
        flash('Campaña archivada. El histórico permanece disponible.', 'success')
    return redirect(url_for('main.campaign_history'))


@main_bp.route("/admin/campaign-draft", methods=["POST"], endpoint="campaign_draft")
@login_required
def campaign_draft():
    """Create an inert annual draft; never start a second operational year."""
    _ensure_admin()
    from app.services.campaign_registry import create_next_campaign_draft
    try:
        year = int(request.form.get('year', ''))
    except (TypeError, ValueError):
        abort(400, description='Año incorrecto.')
    try:
        create_next_campaign_draft(year=year, title=request.form.get('title', ''),
                                   actor_id=current_user.id)
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), 'danger')
    else:
        flash('Borrador anual creado. No admite aún participantes ni pedidos.', 'success')
    return redirect(url_for('main.campaign_history'))


@main_bp.route("/admin/campaign-activate", methods=["POST"], endpoint="campaign_activate")
@login_required
def campaign_activate():
    """Explicit admin-only activation, guarded by a deployment release flag."""
    _ensure_admin()
    from app.services.campaign_activation import activate_prepared_draft, CampaignActivationError
    try:
        year = int(request.form.get('year', ''))
    except (ValueError, TypeError):
        abort(400, description='Año incorrecto.')
    try:
        activate_prepared_draft(year=year, actor_id=current_user.id,
                                confirmation=request.form.get('confirmation', ''))
    except CampaignActivationError as exc:
        db.session.rollback()
        flash(str(exc), 'danger')
    else:
        flash(f'Campaña {year} activada.', 'success')
    return redirect(url_for('main.campaign_history'))


@main_bp.route("/admin/campaign-readiness", methods=["GET"], endpoint="campaign_readiness")
@login_required
def campaign_readiness():
    """Administrative read-only preflight; never activates a campaign."""
    _ensure_admin()
    from app.services.annual_readiness import inspect_annual_readiness
    return render_template('admin_campaign_readiness.html', report=inspect_annual_readiness())


@main_bp.route("/admin/campaign-history", methods=["GET"], endpoint="campaign_history")
@login_required
def campaign_history():
    """Read-only overview of completed campaigns, independent of active-year gating."""
    _ensure_admin()
    from app.services.history_summary import archived_campaign_summaries
    from app.services.active_campaign import current_campaign
    from app.models import Campaign
    drafts = Campaign.query.filter_by(status="draft").order_by(Campaign.year.desc()).all()
    can_create = bool(Campaign.query.first()) and not Campaign.query.filter(~Campaign.status.in_(["archived", "closed"])).first()
    import os
    from app.services.annual_readiness import inspect_annual_readiness
    readiness = inspect_annual_readiness() if drafts else {}
    activation_flag_enabled = os.getenv('ENABLE_ANNUAL_ACTIVATION') == '1'
    return render_template(
        "admin_campaign_history.html",
        campaigns=archived_campaign_summaries(),
        active_campaign=current_campaign(),
        draft_campaigns=drafts,
        can_create_draft=can_create,
        draft_activation=readiness.get('draft_activation', {}),
        activation_flag_enabled=activation_flag_enabled,
    )


@main_bp.route("/admin/simulator", methods=["GET"], endpoint="demo_simulator")
@login_required
def demo_simulator():
    # Never contacts the database: demo values are generated entirely in memory.
    _ensure_admin()
    from app.services.order_simulator import build_demo
    def bounded(name, default, lower, upper):
        value = request.args.get(name, str(default))
        if not value.isascii() or not value.isdecimal() or len(value) > 7:
            abort(400, description="Invalid simulation parameter")
        value = int(value)
        if not lower <= value <= upper:
            abort(400, description="Simulation parameter out of range")
        return value
    limit_config = get_limit_configuration(test_mode=is_test_mode_enabled())
    minimum_total = float(get_annual_setting('limit_minimum_total') or
                          current_app.config.get('MIN_TOTAL_ORDER_AMOUNT', 4800))
    sim_products = bounded("products", 110, 90, 180)
    sim_boost = bounded("boost_ref", 0, 0, sim_products)
    demo = build_demo(seed=bounded("seed", 2026, 1, 999999),
                      users=bounded("users", 36, 5, 120),
                      products=sim_products,
                      limits=limit_config, minimum_total=minimum_total,
                      boost_ref=sim_boost,
                      boost_units=bounded("boost_units", 0, 0, 10000))
    step = bounded("step", 1, 1, 8)
    if demo["intervention"]["reference"] and int(demo["intervention"]["reference"][4:]) > demo["products"]:
        abort(400, description="Reference outside the simulated catalog")
    return render_template("order_simulator.html", demo=demo,
                           step=step, active=demo["stages"][step - 1])


@main_bp.route("/insights", methods=["GET"], endpoint="order_insights")
@login_required
def order_insights():
    from app.services.order_insights import build_insights, capture_snapshot, load_snapshots
    campaign = current_campaign()
    if campaign is None:
        abort(409, description="Register an active campaign before viewing insights.")
    if not current_user.is_admin:
        require_campaign_participant(current_user.id)
    insights = build_insights(user_id=None if current_user.is_admin else current_user.id)
    if current_user.is_admin:
        capture_snapshot(campaign.id, insights)
        insights['history'] = load_snapshots(campaign.id)
    return render_template("order_insights.html", insights=insights, campaign=campaign)


@main_bp.route("/admin", methods=["GET"], endpoint="admin_dashboard")
@login_required
def admin_dashboard():
    _ensure_admin()
    # A new installation has no operational campaign yet.  Keep the
    # campaign-data fail-closed policy, but route the administrator to the
    # read-only campaign registry instead of returning HTTP 409.
    if current_campaign() is None:
        return redirect(url_for('main.campaign_registry'))
    filters = _parse_product_filters()
    page = max(request.args.get("page", 1, type=int), 1)
    per_page = request.args.get("per_page", DEFAULT_PAGE_SIZE, type=int)
    per_page = min(max(per_page, 1), MAX_PAGE_SIZE)
    log_page = max(request.args.get("log_page", 1, type=int), 1)
    log_action = request.args.get("log_action", "").strip()
    log_user_id = request.args.get("log_user", type=int)
    phase = get_current_phase()

    query = products_query()
    if phase in {"final"}:
        query = query
    elif phase in {"order"}:
        query = query.filter(Product.final_selected.is_(True))
        query = query.filter(Product.final_disabled.is_(False))
    query = _apply_product_filters(query, filters)
    ranking_ids = None
    has_filters = any(
        filters[key] for key in ("reference", "name", "colour", "main_group_top", "main_group", "main_group_sub", "present")
    )
    if phase == "final" and not has_filters and not filters["price_order"]:
        ranking_context = get_neutral_ranking(limit=get_limit_configuration(test_mode=is_test_mode_enabled())["final_selection_limit"])
        ranking_ids = [row["id"] for row in ranking_context["rows"]]
        if ranking_ids:
            query = query.filter(Product.id.in_(ranking_ids))

    if filters["votes_only"] == "1":
        query = query.filter(or_(Product.is_locked.is_(True), Product.id.in_(_get_products_with_votes())))

    if ranking_ids:
        rank_map = {pid: idx for idx, pid in enumerate(ranking_ids)}
        rank_case = case(rank_map, value=Product.id, else_=len(ranking_ids) + 1000)
        query = query.order_by(rank_case, Product.id.asc())
    else:
        has_any_votes = (
            db.session.query(UserVote.id).filter(UserVote.product_id == Product.id, UserVote.campaign_id == active_campaign_id()).exists()
        )
        voted_first = case((has_any_votes, 0), else_=1)
        if filters["price_order"] == "asc":
            query = query.order_by(voted_first, Product.price.asc(), Product.id.asc())
        elif filters["price_order"] == "desc":
            query = query.order_by(voted_first, Product.price.desc(), Product.id.asc())
        else:
            query = query.order_by(voted_first, Product.id.asc())

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    aggregates = get_vote_aggregates()
    users = User.query.order_by(User.username.asc()).all()
    user_order_overview, global_order_summary = _build_user_order_overview(users, phase)
    log_query = ActionLog.query.join(User).order_by(ActionLog.created_at.desc(), ActionLog.id.desc())
    if log_action:
        log_query = log_query.filter(ActionLog.action == log_action)
    if log_user_id:
        log_query = log_query.filter(ActionLog.user_id == log_user_id)
    log_pagination = log_query.paginate(page=log_page, per_page=100, error_out=False)
    test_mode = is_test_mode_enabled()
    active_limits = get_limit_configuration(test_mode=test_mode)
    final_context = (
        get_final_selection_snapshot(limit=active_limits["final_selection_limit"])
        if phase in {"final"}
        else None
    )
    ranking_context = ranking_context if phase in {"final"} else None

    final_order_summary = build_final_order_context() if phase in {"order", "final"} else None
    promoted_total = final_order_summary["base_total"] if final_order_summary else 0.0
    min_total = float(get_annual_setting('limit_minimum_total') or current_app.config.get("MIN_TOTAL_ORDER_AMOUNT", 4800))
    order_threshold_met = promoted_total >= min_total
    order_generated_at_raw = get_annual_setting('final_order_generated_at')
    order_generated_at_display = _format_timestamp(order_generated_at_raw)
    order_files = {
        "excel": get_annual_setting('final_order_excel'),
        "piece_pdf": get_annual_setting('final_order_piece_pdf'),
        "user_pdf": get_annual_setting('final_order_user_pdf'),
    }
    order_payment_iban = get_annual_setting('final_order_payment_iban') or ""
    order_payment_due_date = get_annual_setting('final_order_payment_due_date') or ""
    order_finalized = bool(order_generated_at_raw)
    order_tax_input = _get_tax_percentage()
    order_tax_value_preview = promoted_total * (order_tax_input / 100)
    order_shipping_input = _get_config_float("order_shipping_amount")
    last_order_tax = _get_config_float("final_order_last_tax")
    last_order_shipping = _get_config_float("final_order_last_shipping")
    order_action_enabled = (
        phase == "order"
        and bool(final_order_summary and final_order_summary["products"])
        and (order_threshold_met or test_mode)
    )

    main_group_tops = _get_distinct_main_group_tops()
    main_groups = _get_distinct_main_groups()
    main_group_subs = _get_distinct_main_group_subs()
    colour_options = _get_distinct_colours()
    colour_label_map = {option["value"]: option["label"] for option in colour_options}
    colour_filter_label = colour_label_map.get(filters["colour"], filters["colour"])
    color_overview = _build_color_overview()
    last_backup = {
        "file": Config.get("last_backup_file") or "",
        "created_at": _format_timestamp(Config.get("last_backup_created_at")),
        "phase": Config.get("last_backup_phase"),
        "target_phase": Config.get("last_backup_target_phase"),
        "error_log": Config.get("last_backup_error_log") or "",
    }

    return render_template(
        "admin_dashboard.html",
        products=pagination.items,
        pagination=pagination,
        aggregates=aggregates,
        users=users,
        current_phase=phase,
        per_page=per_page,
        final_context=final_context,
        ranking_context=ranking_context,
        final_order_summary=final_order_summary,
        promoted_total=promoted_total,
        min_total=min_total,
        order_threshold_met=order_threshold_met,
        order_action_enabled=order_action_enabled,
        order_files=order_files,
        order_generated_at=order_generated_at_display,
        order_finalized=order_finalized,
        order_payment_iban=order_payment_iban,
        order_payment_due_date=order_payment_due_date,
        order_tax_input=order_tax_input,
        order_tax_value_preview=order_tax_value_preview,
        order_shipping_input=order_shipping_input,
        last_order_tax=last_order_tax,
        last_order_shipping=last_order_shipping,
        **_template_filter_context(filters),
        main_group_top_options=main_group_tops,
        main_group_options=main_groups,
        main_group_sub_options=main_group_subs,
        colour_options=colour_options,
        colour_filter_label=colour_filter_label,
        test_mode_enabled=test_mode,
        active_limits=active_limits,
        global_order_summary=global_order_summary,
        user_order_overview=user_order_overview,
        last_backup=last_backup,
        log_pagination=log_pagination,
        log_action_labels=ACTION_LABELS,
        log_action=log_action,
        log_user_id=log_user_id,
        color_overview=color_overview,
    )


@main_bp.route("/admin/products/toggle-lock", methods=["POST"], endpoint="toggle_lock")
@login_required
def toggle_lock():
    _ensure_admin()
    if _order_is_finalized():
        flash("El pedido final ya está generado. No se pueden modificar las piezas.", "warning")
        return _admin_redirect()
    product_id = request.form.get("product_id", type=int)
    product = products_query().filter_by(id=product_id).first_or_404()
    product.is_locked = _bool_from_form()
    db.session.commit()
    flash(f"Bloqueo actualizado para {product.reference}.", "success")
    return _admin_redirect()


@main_bp.route("/admin/products/toggle-final", methods=["POST"], endpoint="toggle_final_status")
@login_required
def toggle_final_status():
    _ensure_admin()
    if _order_is_finalized():
        flash("El pedido final ya está generado. No se pueden modificar las piezas.", "warning")
        return _admin_redirect()
    product_id = request.form.get("product_id", type=int)
    product = products_query().filter_by(id=product_id).first_or_404()

    action = request.form.get("action")
    desired_state = _bool_from_form()

    if action == "final_disabled":
        product.final_disabled = desired_state
        if desired_state:
            product.final_promoted = False
    elif action == "final_promoted":
        product.final_promoted = desired_state
        if desired_state:
            product.final_disabled = False
    else:
        flash("Acción no reconocida para la referencia final.", "danger")
        return _admin_redirect()

    db.session.commit()

    if get_current_phase() in {"final"}:
        limits = get_limit_configuration()
        summary = compute_final_selection(limit=limits["final_selection_limit"])
        tie_msg = (
            f" Empates pendientes: {len(summary['tie_breakers'])}."
            if summary["tie_breakers"]
            else ""
        )
        flash(
            f"Selección final recalculada ({summary['selected_count']}/{summary['limit']}).{tie_msg}",
            "info",
        )
    else:
        flash("Configuración actualizada.", "success")

    return _admin_redirect()


@main_bp.route("/admin/products/promote-all", methods=["POST"], endpoint="promote_all_products")
@login_required
def promote_all_products():
    _ensure_admin()
    if _order_is_finalized():
        flash("El pedido final ya está generado. No se pueden promover más piezas.", "warning")
        return _admin_redirect()
    if get_current_phase() != "final":
        flash("Solo puedes promover todas las piezas durante la fase final.", "warning")
        return _admin_redirect()

    ids_with_votes = _get_products_with_votes()
    if not ids_with_votes:
        flash("No hay piezas con votos para promover.", "warning")
        return _admin_redirect()

    products_query().filter(Product.id.in_(ids_with_votes)).update(
        {
            Product.final_promoted: True,
            Product.final_disabled: False,
        },
        synchronize_session=False,
    )
    db.session.commit()

    limits = get_limit_configuration()
    summary = compute_final_selection(limit=limits["final_selection_limit"])
    flash(
        f"Todas las piezas con votos han sido promovidas ({summary['selected_count']}/{summary['limit']}).",
        "success",
    )
    return _admin_redirect()


@main_bp.route("/admin/users/toggle-access", methods=["POST"], endpoint="toggle_user_active")
@login_required
def toggle_user_active():
    _ensure_admin()
    user_id = request.form.get("user_id", type=int)
    user = User.query.get_or_404(user_id)
    desired_state = request.form.get("desired_state", type=int)
    user.active = bool(desired_state)
    db.session.commit()
    state_text = "desbloqueado" if user.active else "bloqueado"
    flash(f"Usuario {user.username} {state_text}.", "success")
    return _admin_redirect(active_tab="usuarios")


@main_bp.route("/admin/users/toggle-admin", methods=["POST"], endpoint="toggle_user_admin")
@login_required
def toggle_user_admin():
    _ensure_admin()
    user_id = request.form.get("user_id", type=int)
    user = User.query.get_or_404(user_id)
    desired_state = request.form.get("desired_state", type=int)
    user.is_admin = bool(desired_state)
    db.session.commit()
    state_text = "ahora es administrador" if user.is_admin else "ya no es administrador"
    flash(f"{user.username} {state_text}.", "success")
    return _admin_redirect(active_tab="usuarios")


@main_bp.route("/admin/users/validate-declaration", methods=["POST"], endpoint="validate_declaration")
@login_required
def validate_declaration():
    _ensure_admin()
    user_id = request.form.get("user_id", type=int)
    user = User.query.get_or_404(user_id)
    from app.services.active_campaign import current_campaign, current_membership
    membership = current_membership(user.id)
    if membership is None or not membership.signed_document:
        abort(400, description='No signed document uploaded for current campaign')
    from app.services.campaign_participation import review_signed_document
    if current_campaign() is not None:
        membership = current_membership(user.id)
        if membership is None:
            abort(403, description='Not enrolled in active campaign')
        review_signed_document(membership, current_user, approve=True)
    log_user_action(current_user.id, 'document_approved', f'Participant {user.id}')
    clear_declaration_issue(user.id)
    db.session.commit()
    flash(f"Declaración jurada de {user.username} validada.", "success")
    return _admin_redirect(active_tab="usuarios")


@main_bp.route("/admin/users/delete-declaration", methods=["POST"], endpoint="delete_declaration")
@login_required
def delete_declaration():
    _ensure_admin()
    user_id = request.form.get("user_id", type=int)
    user = User.query.get_or_404(user_id)
    from app.services.active_campaign import current_membership
    membership = current_membership(user.id)
    if membership is None:
        abort(403)
    removed = bool(membership.signed_document)
    membership.signed_document = None
    membership.status = 'pending_commitment'
    membership.document_approved_at = None
    membership.document_approved_by = None
    # Retain the physical PDF for archived memberships referencing it.
    clear_declaration_issue(user.id)
    db.session.commit()
    if removed:
        flash(f"Declaración jurada de {user.username} eliminada.", "success")
    else:
        flash(f"{user.username} no tenía una declaración cargada.", "info")
    return _admin_redirect(active_tab="usuarios")


@main_bp.route("/admin/users/invalidate-declaration", methods=["POST"], endpoint="invalidate_declaration")
@login_required
def invalidate_declaration():
    _ensure_admin()
    user_id = request.form.get("user_id", type=int)
    user = User.query.get_or_404(user_id)
    from app.services.active_campaign import current_membership
    membership = current_membership(user.id)
    if membership is None:
        abort(403)
    membership.status = 'rejected'
    membership.document_approved_at = None
    membership.document_approved_by = None
    log_user_action(current_user.id, 'document_rejected', f'Participant {user.id}')
    reason = request.form.get("reason", "").strip() or "Tu declaración jurada anterior no era válida. Sube un nuevo archivo corregido."
    set_declaration_issue(user.id, reason)
    db.session.commit()
    flash(f"Declaración jurada de {user.username} marcada como no válida.", "warning")
    return _admin_redirect(active_tab="usuarios")


@main_bp.route("/admin/users/reset-password", methods=["POST"], endpoint="reset_user_password")
@login_required
def reset_user_password():
    _ensure_admin()
    user_id = request.form.get("user_id", type=int)
    user = User.query.get_or_404(user_id)
    default_password = current_app.config.get("DEFAULT_USER_PASSWORD")
    if not default_password or len(default_password) < 12:
        abort(503, description="Configure DEFAULT_USER_PASSWORD securely")
    user.set_password(default_password)
    user.must_change_password = True
    log_user_action(
        user.id,
        "password_reset",
        detail=f"Restablecida por {current_user.username}.",
    )
    db.session.commit()
    flash(f"Contraseña de {user.username} restablecida.", "success")
    return _admin_redirect(active_tab="usuarios")


@main_bp.route("/admin/users/declaration/<int:user_id>", methods=["GET"], endpoint="download_declaration")
@login_required
def download_declaration(user_id: int):
    _ensure_admin()
    user = User.query.get_or_404(user_id)
    from app.services.active_campaign import current_membership
    membership = current_membership(user.id)
    if membership is None or not membership.signed_document:
        abort(404)
    name = membership.signed_document
    if os.path.basename(name) != name:
        abort(404)
    folder = current_app.config['DECLARATION_UPLOAD_FOLDER']
    if not os.path.isfile(os.path.join(folder, name)):
        abort(404)
    return send_from_directory(folder, name, as_attachment=True, download_name=name)


@main_bp.route("/admin/phase/activate-second", methods=["POST"], endpoint="activate_phase2")
@login_required
def activate_phase2():
    _ensure_admin()
    if get_current_phase() != "first":
        flash("Solo puedes activar la segunda fase desde la primera.", "warning")
        return _admin_redirect()
    _attempt_phase_backup("first", "second")
    set_current_phase("second")
    flash("Segunda fase activada.", "success")
    return _admin_redirect()


@main_bp.route("/admin/phase/advance-final", methods=["POST"], endpoint="advance_phase")
@login_required
def advance_phase():
    _ensure_admin()
    if get_current_phase() != "second":
        flash("Solo puedes pasar a la fase final desde la segunda fase.", "warning")
        return _admin_redirect()
    test_mode = is_test_mode_enabled()
    min_total = float(get_annual_setting('limit_minimum_total') or current_app.config.get("MIN_TOTAL_ORDER_AMOUNT", 4800))
    current_total = _calculate_global_order_total()
    if current_total < min_total:
        flash(
            f"Avanzando a fase final con un total de {current_total:.2f}€ (mínimo habitual {min_total:.2f}€).",
            "info",
        )
    _attempt_phase_backup("second", "final")
    set_current_phase("final")
    limits = get_limit_configuration()
    summary = compute_final_selection(limit=limits["final_selection_limit"])
    flash(
        f"Fase final activada ({summary['selected_count']}/{summary['limit']} seleccionadas).",
        "success",
    )
    return redirect(url_for('main.admin_dashboard', active_tab='ranking'))


@main_bp.route("/admin/phase/advance-order", methods=["POST"], endpoint="advance_order_phase")
@login_required
def advance_order_phase():
    _ensure_admin()
    if get_current_phase() != "final":
        flash("Solo puedes liberar la fase de pedido desde la fase final.", "warning")
        return _admin_redirect()
    limits = get_limit_configuration()
    # Preflight must not persist a new selection or create a backup when
    # ties / over-limit references still prevent the transition.
    summary = compute_final_selection(limit=limits["final_selection_limit"], persist=False)
    if summary["tie_breakers"] or summary["over_limit"] or not summary["selected_count"]:
        flash("Resuelve la selección final antes de activar pedidos.", "danger")
        return _admin_redirect(active_tab='ranking')
    _attempt_phase_backup("final", "order")
    # Selection, order floors and phase must succeed or roll back together.
    from app.services.order_materialization import (
        materialize_selected_commitments, assert_selected_commitments_materialized,
    )
    try:
        summary = compute_final_selection(limit=limits["final_selection_limit"], commit=False)
        rows_created, units_added = materialize_selected_commitments()
        # Verify the persisted vote floors before changing the campaign phase.
        # This query sees the pending inserts in the same SQLAlchemy transaction.
        assert_selected_commitments_materialized()
        set_current_phase("order", commit=False)
        db.session.commit()
    except Exception:
        # Roll back even for unexpected failures (e.g. a runtime error in a
        # service), not only known validation or database exceptions.
        db.session.rollback()
        current_app.logger.exception("Error activando pedidos de forma atomica")
        flash("No se ha activado la fase de pedido; se han revertido los cambios.", "danger")
        return _admin_redirect(active_tab='ranking')
    flash(
        f"Fase de pedido activada ({summary['selected_count']}/{summary['limit']} seleccionadas). "
        f"Compromisos trasladados: {rows_created} registros, {units_added} unidades.",
        "success",
    )
    return redirect(url_for('main.admin_dashboard', active_tab='pedidos'))


@main_bp.route("/admin/clean-data", methods=["POST"], endpoint="clean_data")
@login_required
def clean_data():
    _ensure_admin()
    # Destructive cleanup is deliberately disabled until campaigns have
    # independent, verified persistence and archives. Never delete annual
    # records from an unversioned database through a web form.
    abort(409, description=(
        'El borrado anual está deshabilitado hasta disponer de campañas '
        'independientes y un archivo histórico verificable.'
    ))


@main_bp.route("/admin/test-mode", methods=["POST"], endpoint="toggle_test_mode")
@login_required
def toggle_test_mode():
    _ensure_admin()
    desired_state = request.form.get("enable") == "1"
    current_state = is_test_mode_enabled()

    if desired_state == current_state:
        state_text = "activo" if current_state else "desactivado"
        flash(f"El modo de pruebas ya está {state_text}.", "info")
        return _admin_redirect()

    Config.set(TEST_MODE_KEY, "1" if desired_state else "0")

    if current_state and not desired_state:
        # Switching off test mode must NEVER silently erase real records.
        log_user_action(
            current_user.id,
            "admin_toggle_test_mode",
            detail=f"Desactivado por {current_user.username}. Datos conservados.",
            commit=True,
        )
        flash("Modo de pruebas desactivado. Se han conservado todos los datos.", "success")
    elif desired_state:
        log_user_action(
            current_user.id,
            "admin_toggle_test_mode",
            detail=f"Activado por {current_user.username}.",
            commit=True,
        )
        flash("Modo de pruebas activado con límites reducidos.", "success")
    else:
        log_user_action(
            current_user.id,
            "admin_toggle_test_mode",
            detail=f"Actualizado por {current_user.username}.",
            commit=True,
        )
        flash("Modo de pruebas actualizado.", "info")

    return _admin_redirect()


@main_bp.route("/admin/backup/create", methods=["POST"], endpoint="create_backup")
@login_required
def create_backup_endpoint():
    _ensure_admin()
    phase_at_backup = request.form.get("phase_at_backup") or Config.get("last_backup_phase") or get_current_phase()
    target_phase = request.form.get("target_phase") or Config.get("last_backup_target_phase") or get_current_phase()
    Config.set("last_backup_phase", phase_at_backup)
    Config.set("last_backup_target_phase", target_phase)
    try:
        create_phase_backup(phase_at_backup=phase_at_backup, target_phase=target_phase)
        flash(f"Backup creado para {phase_at_backup} → {target_phase}.", "success")
    except Exception as exc:  # noqa: BLE001
        write_backup_error_log(exc)
        flash("No se pudo crear el backup manual. Descarga el log para revisarlo.", "danger")
    return _admin_redirect(active_tab="productos")


@main_bp.route("/admin/backup/download", methods=["GET"], endpoint="download_backup")
@login_required
def download_backup():
    _ensure_admin()
    path = Config.get("last_backup_file")
    if not path or not os.path.isfile(path):
        abort(404)
    filename = os.path.basename(path)
    return send_file(path, as_attachment=True, download_name=filename)


@main_bp.route("/admin/backup/error-log", methods=["GET"], endpoint="download_backup_log")
@login_required
def download_backup_log():
    _ensure_admin()
    path = Config.get("last_backup_error_log")
    if not path or not os.path.isfile(path):
        abort(404)
    filename = os.path.basename(path)
    return send_file(path, as_attachment=True, download_name=filename)


@main_bp.route("/admin/backup/restore", methods=["POST"], endpoint="restore_backup")
@login_required
def restore_backup_endpoint():
    _ensure_admin()
    # The old online ZIP restore was unsafe if connections remained open.
    # Keep the endpoint to fail closed for old bookmarks, but do not apply data.
    abort(409, description=(
        'Restauracion online deshabilitada. Deten el servicio y usa '
        'sh scripts/restore_offline.sh RUTA_DEL_BACKUP.zip en el servidor.'
    ))


@main_bp.route("/admin/order/costs", methods=["POST"], endpoint="update_order_costs")
@login_required
def update_order_costs():
    _ensure_admin()
    if _order_is_finalized():
        flash("El pedido final ya está generado. No se pueden actualizar los costes.", "warning")
        return _admin_redirect()
    tax_percent = _coerce_positive_float(request.form.get("tax_amount"))
    shipping_amount = _coerce_positive_float(request.form.get("shipping_amount"))
    set_annual_setting('order_tax_percent', f"{tax_percent:.4f}")
    set_annual_setting('order_shipping_amount', f"{shipping_amount:.2f}")
    flash("Costes de impuestos y transporte actualizados.", "success")
    return _admin_redirect()


@main_bp.route("/admin/order/generate", methods=["POST"], endpoint="generate_order_exports")
@login_required
def generate_order_exports_route():
    _ensure_admin()
    # The same phase policy applies to the UI and the POST endpoint.
    # Reject direct submissions during selection or before order materialization.
    if get_current_phase() != "order":
        flash("Libera primero la fase de pedido para generar el Excel definitivo.", "warning")
        return _admin_redirect()
    if _order_is_finalized():
        flash("El pedido final ya fue generado. No se pueden realizar más cambios.", "warning")
        return _admin_redirect()
    summary = build_final_order_context()
    if not summary["products"]:
        flash("No hay referencias promovidas con votos para generar el pedido final.", "warning")
        return _admin_redirect()

    min_total = float(get_annual_setting('limit_minimum_total') or current_app.config.get("MIN_TOTAL_ORDER_AMOUNT", 4800))
    test_mode = is_test_mode_enabled()
    if not test_mode and summary["base_total"] < min_total:
        flash(
            f"El total promovido ({summary['base_total']:.2f} €) no alcanza el mínimo de {min_total:.2f} €.",
            "danger",
        )
        return _admin_redirect()

    tax_percent = _get_tax_percentage()
    shipping_amount = _get_config_float("order_shipping_amount")

    try:
        tax_amount = summary["base_total"] * (tax_percent / 100)
        files = generate_order_files(
            summary,
            tax_amount,
            shipping_amount,
            get_annual_setting('final_order_payment_iban') or None,
            get_annual_setting('final_order_payment_due_date') or None,
        )
    except Exception as exc:  # noqa: BLE001
        flash(f"No se pudo generar el pedido final: {exc}", "danger")
        return _admin_redirect()

    timestamp = datetime.utcnow().isoformat()
    set_annual_setting('final_order_excel', files["excel"])
    set_annual_setting('final_order_piece_pdf', files.get("piece_pdf") or files.get("piece"))
    set_annual_setting('final_order_user_pdf', files.get("user_pdf") or files.get("user"))
    set_annual_setting('final_order_generated_at', timestamp)
    set_annual_setting('final_order_last_tax', f"{tax_amount:.2f}")
    set_annual_setting('final_order_last_shipping', f"{shipping_amount:.2f}")

    flash("Pedido final generado y archivos listos para descargar.", "success")
    return _admin_redirect()


@main_bp.route("/admin/order/regenerate", methods=["POST"], endpoint="regenerate_order_exports")
@login_required
def regenerate_order_exports_route():
    _ensure_admin()
    if not _order_is_finalized():
        flash("El pedido final aún no está generado. Usa 'Realizar pedido'.", "warning")
        return _admin_redirect()

    summary = build_final_order_context()
    if not summary["products"]:
        flash("No hay referencias promovidas con votos para regenerar los archivos.", "warning")
        return _admin_redirect()

    _regenerate_order_exports_in_background(
        get_annual_setting('final_order_payment_iban') or None,
        get_annual_setting('final_order_payment_due_date') or None,
    )
    flash("La regeneracion de archivos se ha lanzado en segundo plano.", "success")
    return _admin_redirect()


@main_bp.route("/admin/order/payment-details", methods=["POST"], endpoint="update_order_payment_details")
@login_required
def update_order_payment_details():
    _ensure_admin()
    iban = (request.form.get("payment_iban") or "").strip().replace(" ", "").upper()
    due_date_raw = (request.form.get("payment_due_date") or "").strip()
    active_tab = request.form.get("active_tab") or "productos"

    if not iban:
        flash("Debes indicar un IBAN.", "warning")
        return _admin_redirect(active_tab=active_tab)
    if not _is_valid_iban(iban):
        flash("El IBAN no es valido.", "warning")
        return _admin_redirect(active_tab=active_tab)
    if not due_date_raw:
        flash("Debes indicar una fecha limite.", "warning")
        return _admin_redirect(active_tab=active_tab)

    due_date = _parse_iso_date(due_date_raw)
    if due_date is None:
        flash("La fecha limite no es valida.", "warning")
        return _admin_redirect(active_tab=active_tab)
    if due_date <= date.today():
        flash("La fecha limite debe ser posterior a hoy.", "warning")
        return _admin_redirect(active_tab=active_tab)

    set_annual_setting('final_order_payment_iban', iban)
    set_annual_setting('final_order_payment_due_date', due_date.isoformat())

    if _order_is_finalized():
        _regenerate_order_exports_in_background(iban, due_date.isoformat())
        flash("Datos de pago guardados. Los archivos se estan regenerando en segundo plano.", "success")
        return _admin_redirect(active_tab=active_tab)

    flash("Datos de pago guardados.", "success")
    return _admin_redirect(active_tab=active_tab)


@main_bp.route("/admin/order/download/<string:kind>", methods=["GET"], endpoint="download_order_file")
@login_required
def download_order_file(kind: str):
    _ensure_admin()
    mapping = {
        "excel": get_annual_setting('final_order_excel'),
        "piece": get_annual_setting('final_order_piece_pdf'),
        "user": get_annual_setting('final_order_user_pdf'),
    }
    filename = mapping.get(kind)
    if not filename:
        abort(404)
    from app.services.export_path_safety import safe_export_path
    folder = current_app.config["ORDER_EXPORT_FOLDER"]
    suffixes = {"excel": ".xlsx", "piece": ".pdf", "user": ".zip"}
    path = safe_export_path(folder, filename, suffix=suffixes[kind])
    if path is None:
        abort(404)
    return send_from_directory(folder, path.name, as_attachment=True)


@main_bp.route("/admin/orders/update", methods=["POST"], endpoint="admin_update_order")
@login_required
def admin_update_order():
    _ensure_admin()
    vote_id = request.form.get("vote_id", type=int)
    quantity = request.form.get("quantity", type=int)
    if not vote_id:
        flash("Referencia de pedido no válida.", "warning")
        return _admin_redirect(active_tab="pedidos")
    if quantity is None or quantity <= 0:
        flash("Indica una cantidad mayor que cero.", "warning")
        return _admin_redirect(active_tab="pedidos")
    vote = votes_query().filter(UserVote.id == vote_id).first_or_404()
    from app.services.vote_commitments import assert_nondecreasing_vote
    assert_nondecreasing_vote(vote.quantity, quantity)
    require_campaign_participant(vote.user_id)
    product = validate_product_campaign(vote.product)
    user = vote.user
    if _order_is_finalized():
        abort(409, description='El pedido está cerrado; hay que reabrirlo explícitamente.')
    valid, reason = _validate_quantity_for_product(product.price or 0, quantity)
    if not valid:
        abort(400, description=reason)
    current_total = _calculate_user_total(user.id)
    proposed_total = current_total + (quantity - vote.quantity) * product.price
    if proposed_total > get_limit_configuration()['phase_one_order_limit'] + 0.00001:
        abort(400, description='El pedido supera el límite individual.')
    vote.quantity = quantity
    log_user_action(
        current_user.id,
        "admin_order_update",
        detail=(
            f"{current_user.username} actualizo {product.reference} "
            f"({product.name or 'sin nombre'}) para {user.username}: {quantity} uds."
        ),
    )
    db.session.commit()
    flash(
        f"Pedido actualizado ({quantity} uds) para {user.username} - {product.reference}.",
        "success",
    )
    return _admin_redirect(active_tab="pedidos")


@main_bp.route("/admin/orders/add", methods=["POST"], endpoint="admin_add_order")
@login_required
def admin_add_order():
    _ensure_admin()
    user_id = request.form.get("user_id", type=int)
    quantity = request.form.get("quantity", type=int)
    reference = (request.form.get("reference") or "").strip()
    product_id = request.form.get("product_id", type=int)
    if not user_id:
        flash("Usuario no válido.", "warning")
        return _admin_redirect(active_tab="pedidos")
    if quantity is None or quantity <= 0:
        flash("Indica una cantidad mayor que cero.", "warning")
        return _admin_redirect(active_tab="pedidos")
    user = User.query.get_or_404(user_id)
    require_campaign_participant(user.id)
    product = None
    if product_id:
        product = products_query().filter_by(id=product_id).first()
    if not product and reference:
        product = (
            products_query().filter(func.lower(Product.reference) == reference.lower()).first()
        )
    if not product:
        flash("No se encontró la referencia indicada.", "warning")
        return _admin_redirect(active_tab="pedidos")

    if _order_is_finalized():
        abort(409, description='El pedido está cerrado; hay que reabrirlo explícitamente.')
    vote = votes_query().filter_by(user_id=user.id, product_id=product.id).first()
    from app.services.vote_commitments import assert_nondecreasing_vote
    assert_nondecreasing_vote(vote.quantity if vote else 0, quantity)
    valid, reason = _validate_quantity_for_product(product.price or 0, quantity)
    if not valid:
        abort(400, description=reason)
    current_total = _calculate_user_total(user.id)
    proposed_total = current_total + (quantity - (vote.quantity if vote else 0)) * product.price
    if proposed_total > get_limit_configuration()['phase_one_order_limit'] + 0.00001:
        abort(400, description='El pedido supera el límite individual.')
    if vote:
        vote.quantity = quantity
        log_user_action(
            current_user.id,
            "admin_order_update",
            detail=(
                f"{current_user.username} actualizo {product.reference} "
                f"({product.name or 'sin nombre'}) para {user.username}: {quantity} uds."
            ),
        )
    else:
        vote = UserVote(
            campaign_id=active_campaign_id(),
            user_id=user.id,
            product_id=product.id,
            quantity=quantity,
            phase=get_current_phase(),
        )
        db.session.add(vote)
        log_user_action(
            current_user.id,
            "admin_order_add",
            detail=(
                f"{current_user.username} anadio {product.reference} "
                f"({product.name or 'sin nombre'}) para {user.username}: {quantity} uds."
            ),
        )
    db.session.commit()
    flash(
        f"Pedido actualizado ({quantity} uds) para {user.username} - {product.reference}.",
        "success",
    )
    return _admin_redirect(active_tab="pedidos")


@main_bp.route("/admin/colors/update", methods=["POST"], endpoint="update_color_map")
@login_required
def update_color_map():
    _ensure_admin()
    lego_name = (request.form.get("lego_name") or "").strip()
    bl_name = (request.form.get("bl_name") or "").strip()
    if not lego_name:
        flash("Debes indicar el color original.", "warning")
        return _admin_redirect(active_tab="colores")

    entry = ColorMap.query.filter(func.lower(ColorMap.lego_name) == lego_name.lower()).first()
    if entry:
        entry.lego_name = lego_name
        entry.bl_name = bl_name or None
    else:
        entry = ColorMap(lego_name=lego_name, bl_name=bl_name or None)
        db.session.add(entry)

    products_query().filter(func.lower(Product.colour_id) == lego_name.lower()).update(
        {"color_bl": bl_name or None},
        synchronize_session=False,
    )
    db.session.commit()
    flash(f"Color BL actualizado para {lego_name}.", "success")
    return _admin_redirect(active_tab="colores")


@main_bp.route("/admin/upload-data", methods=["GET", "POST"], endpoint="upload_data")
@login_required
def upload_data():  # type: ignore[override]
    _ensure_admin()
    report = None
    preview = None
    # Bind every pending preview to the active year and administrator.
    campaign_id = active_campaign_id()
    pending_upload = bool(session.get("pending_excel_upload"))
    if request.method == "POST":
        if request.form.get("cancel_upload"):
            _clear_pending_excel_upload()
            flash("Carga cancelada.", "info")
            return redirect(url_for("main.upload_data"))
        if request.form.get("confirm_upload"):
            pending = session.get("pending_excel_upload") or {}
            path = pending.get("path")
            if not _pending_catalog_matches(pending, campaign_id, current_user.id):
                _clear_pending_excel_upload()
                flash("La campana o el administrador han cambiado; vuelve a subir el Excel.", "warning")
                return redirect(url_for("main.upload_data"))
            if not path or not os.path.exists(path):
                _clear_pending_excel_upload()
                flash("No se encontro el archivo pendiente para confirmar.", "warning")
                return redirect(url_for("main.upload_data"))
            with open(path, "rb") as handle:
                content = handle.read()
            report = _handle_products_excel_upload(content=content)
            _clear_pending_excel_upload()
            pending_upload = False
        else:
            file = request.files.get("excel_file")
            if not file or not file.filename:
                flash("Selecciona un archivo Excel valido (.xlsx).", "warning")
                return render_template("upload_excel.html", report=report)
            content = file.read()
            if products_query().count() > 0:
                preview = _build_products_excel_preview(content)
                if preview is None:
                    return render_template("upload_excel.html", report=report)
                _clear_pending_excel_upload()
                path = _save_pending_excel_upload(content)
                session["pending_excel_upload"] = {"path": path, "filename": file.filename, "campaign_id": campaign_id, "admin_id": current_user.id}
                pending_upload = True
            else:
                report = _handle_products_excel_upload(content=content)
    if request.method == "GET" and pending_upload and preview is None:
        pending = session.get("pending_excel_upload") or {}
        path = pending.get("path")
        if not _pending_catalog_matches(pending, campaign_id, current_user.id):
            _clear_pending_excel_upload()
            pending_upload = False
            flash("La vista previa ha caducado; vuelve a subir el Excel.", "warning")
        elif path and os.path.exists(path):
            with open(path, "rb") as handle:
                preview = _build_products_excel_preview(handle.read())
        else:
            _clear_pending_excel_upload()
            pending_upload = False
    return render_template(
        "upload_excel.html",
        report=report,
        preview=preview,
        pending_upload=pending_upload,
    )


@main_bp.route("/admin/upload-users", methods=["GET", "POST"], endpoint="upload_users")
@login_required
def upload_users():  # type: ignore[override]
    _ensure_admin()
    report = None
    if request.method == "POST":
        report = _handle_users_csv_upload()
    return render_template("upload_users_csv.html", report=report)


@main_bp.route("/admin/campaign-draft/<int:campaign_id>/participants", methods=["GET", "POST"], endpoint="draft_participants")
@login_required
def draft_participants(campaign_id):
    """Import only annual enrolments into an inert draft, not prior approvals."""
    _ensure_admin()
    from app.models import Campaign
    draft = Campaign.query.filter_by(id=campaign_id, status='draft').one_or_none()
    if draft is None:
        abort(404)
    report = None
    if request.method == 'POST':
        report = _handle_users_csv_upload(draft_campaign_id=campaign_id)
    return render_template('upload_users_csv.html', report=report, draft=draft)


@main_bp.route("/admin/campaign-draft/<int:campaign_id>/catalog", methods=["GET", "POST"], endpoint="draft_catalog")
@login_required
def draft_catalog(campaign_id):
    """Import an Excel catalog exclusively into a non-operational annual draft."""
    _ensure_admin()
    from app.models import Campaign
    from app.services.draft_catalog_import import import_draft_catalog

    draft = Campaign.query.filter_by(id=campaign_id, status='draft').one_or_none()
    if draft is None:
        abort(404)
    report = None
    if request.method == 'POST':
        file = request.files.get('excel_file')
        if not file or not file.filename or not file.filename.lower().endswith('.xlsx'):
            flash('Selecciona un archivo .xlsx válido.', 'warning')
        else:
            content = file.read()
            if len(content) > 15 * 1024 * 1024:
                abort(413)
            parsed, error = _parse_products_excel(content)
            if error:
                flash(error, 'danger')
            elif parsed['errors'] or parsed['skipped'] or not parsed['products']:
                flash('El Excel contiene errores o no incluye referencias válidas. No se ha importado nada.', 'danger')
                report = parsed
            else:
                try:
                    report = import_draft_catalog(campaign_id, parsed['products'], actor_id=current_user.id)
                    flash('Catálogo del borrador importado correctamente.', 'success')
                except ValueError as exc:
                    db.session.rollback()
                    flash(str(exc), 'danger')
    return render_template('draft_catalog.html', draft=draft, report=report)


@main_bp.route("/admin/set-dates", methods=["GET", "POST"], endpoint="set_dates")
@login_required
def set_dates():  # type: ignore[override]
    _ensure_admin()
    if current_campaign() is None:
        abort(409, description="No hay una campaña activa para configurar fechas.")
    if request.method == "POST":
        set_annual_setting("voting_start", request.form.get("voting_start"))
        set_annual_setting("voting_end", request.form.get("voting_end"))
        set_annual_setting("second_phase_date", request.form.get("second_phase_date"))
        set_annual_setting("order_deadline", request.form.get("order_deadline"))
        flash("Fechas actualizadas.", "success")
        return _admin_redirect()

    today = date.today().isoformat()
    context = {
        "voting_start": get_annual_setting("voting_start") or today,
        "voting_end": get_annual_setting("voting_end") or today,
        "second_phase_date": get_annual_setting("second_phase_date") or today,
        "order_deadline": get_annual_setting("order_deadline") or today,
    }
    return render_template("set_dates.html", **context)


def _collect_user_votes(user_id: int) -> Tuple[Dict[int, Dict[str, object]], float]:
    rows = (
        db.session.query(
            UserVote,
            Product.price,
            Product.name,
            Product.reference,
            Product.colour_id,
            Product.color_bl,
            Product.present_in_2025,
            Product.final_disabled,
            Product.final_selected,
        )
        .outerjoin(Product, Product.id == UserVote.product_id)
        .filter(UserVote.user_id == user_id, UserVote.campaign_id == active_campaign_id(), Product.campaign_id == active_campaign_id())
        .all()
    )
    user_votes: Dict[int, Dict[str, object]] = {}
    total_order = 0.0
    for vote, price, name, reference, colour_id, color_bl, present_in_2025, final_disabled, final_selected in rows:
        user_votes[vote.product_id] = {
            "vote": vote,
            "price": float(price or 0),
            "name": name,
            "reference": reference,
            "colour_id": colour_id,
            "color_bl": color_bl,
            "present_in_2025": present_in_2025,
            "final_disabled": bool(final_disabled),
            "final_selected": bool(final_selected),
        }
        total_order += (vote.quantity or 0) * float(price or 0)
    return user_votes, total_order


def _build_user_order_overview(users: List[User], phase: str) -> Tuple[List[Dict[str, object]], Dict[str, object]]:
    overview: List[Dict[str, object]] = []
    user_lookup: Dict[int, Dict[str, object]] = {}
    for user in users:
        summary = {
            "user": user,
            "orders": [],
            "total_quantity": 0,
            "total_amount": 0.0,
        }
        user_lookup[user.id] = summary
        overview.append(summary)

    reference_totals: Dict[int, Dict[str, object]] = {}
    global_total = 0.0

    query = (
        db.session.query(
            UserVote.id.label("vote_id"),
            UserVote.user_id.label("user_id"),
            UserVote.quantity.label("quantity"),
            UserVote.initial_quantity.label("initial_quantity"),
            Product.id.label("product_id"),
            Product.reference.label("reference"),
            Product.name.label("name"),
            Product.price.label("price"),
            Product.image_url.label("image_url"),
        )
        .join(User, User.id == UserVote.user_id)
        .join(Product, Product.id == UserVote.product_id)
        .filter(UserVote.campaign_id == active_campaign_id(), Product.campaign_id == active_campaign_id())
        .order_by(User.username.asc(), Product.reference.asc())
    )
    if phase in {"order", "final"}:
        query = query.filter(Product.final_selected.is_(True))
        query = query.filter(Product.final_disabled.is_(False))
    rows = query.all()
    for row in rows:
        summary = user_lookup.get(row.user_id)
        if not summary:
            continue
        quantity = int(row.quantity or 0)
        price = float(row.price or 0.0)
        summary["orders"].append(
            {
                "vote_id": row.vote_id,
                "product_id": row.product_id,
                "reference": row.reference,
                "name": row.name,
                "price": price,
                "image_url": row.image_url,
                "quantity": quantity,
                "initial_quantity": row.initial_quantity,
                "total": quantity * price,
            }
        )
        summary["total_quantity"] += quantity
        line_total = quantity * price
        summary["total_amount"] += line_total
        if row.product_id not in reference_totals:
            reference_totals[row.product_id] = {
                "product_id": row.product_id,
                "reference": row.reference,
                "name": row.name,
                "price": price,
                "image_url": row.image_url,
                "total_quantity": 0,
                "total_amount": 0.0,
                "num_votes": 0,
            }
        reference_totals[row.product_id]["total_quantity"] += quantity
        reference_totals[row.product_id]["total_amount"] += line_total
        reference_totals[row.product_id]["num_votes"] += 1
        global_total += line_total

    reference_list = sorted(
        reference_totals.values(),
        key=lambda item: (
            -int(item.get("num_votes") or 0),
            -int(item.get("total_quantity") or 0),
            -float(item.get("total_amount") or 0.0),
            (item.get("reference") or "").lower(),
        ),
    )
    summary_payload = {
        "references": reference_list,
        "total_amount": global_total,
    }
    return overview, summary_payload


def _coerce_positive_float(value: str | None) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(number, 0.0)


def _get_config_float(key: str, default: float = 0.0) -> float:
    value = get_annual_setting(key) if key in ANNUAL_KEYS else Config.get(key)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _get_tax_percentage() -> float:
    value = get_annual_setting('order_tax_percent')
    try:
        return max(float(value), 0.0)
    except (TypeError, ValueError):
        return 0.0


def _format_timestamp(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return value
    return parsed.strftime("%d/%m/%Y %H:%M")


def _parse_product_filters() -> Dict[str, str]:
    return {
        "reference": request.args.get("reference", "").strip(),
        "name": request.args.get("name", "").strip(),
        "colour": request.args.get("colour", "").strip(),
        "main_group_top": request.args.get("main_group_top", "").strip(),
        "main_group": request.args.get("main_group", "").strip(),
        "main_group_sub": request.args.get("main_group_sub", "").strip(),
        "present": request.args.get("present", "").strip(),
        "price_order": request.args.get("price_order", "").strip(),
        "votes_only": request.args.get("votes_only", "").strip(),
    }


def _apply_product_filters(query, filters):
    if filters["reference"]:
        query = query.filter(Product.reference.ilike(f"%{filters['reference']}%"))
    if filters["name"]:
        query = query.filter(Product.name.ilike(f"%{filters['name']}%"))
    if filters["colour"]:
        query = query.filter(Product.colour_id.ilike(f"%{filters['colour']}%"))
    if filters["main_group_top"]:
        query = query.filter(Product.main_group_top.ilike(f"%{filters['main_group_top']}%"))
    if filters["main_group"]:
        query = query.filter(Product.main_group.ilike(f"%{filters['main_group']}%"))
    if filters["main_group_sub"]:
        query = query.filter(Product.main_group_sub.ilike(f"%{filters['main_group_sub']}%"))
    if filters["present"]:
        normalized = filters["present"].lower()
        if normalized in {"2025", "yes", "si", "true", "1"}:
            query = query.filter(Product.present_in_2025.is_(True))
        elif normalized in {"new", "no", "false", "0"}:
            query = query.filter(Product.present_in_2025.is_(False))
    return query


def _template_filter_context(filters: Dict[str, str]):
    return {
        "reference_search": filters["reference"],
        "name_search": filters["name"],
        "colour_filter": filters["colour"],
        "main_group_top_filter": filters["main_group_top"],
        "main_group_filter": filters["main_group"],
        "main_group_sub_filter": filters["main_group_sub"],
        "present_filter": filters["present"],
        "price_order": filters["price_order"],
        "votes_only": filters["votes_only"],
    }


def _dashboard_redirect():
    page = request.form.get("page", type=int) or request.args.get("page", type=int) or 1
    page = max(page, 1)
    per_page = request.form.get("per_page", type=int) or request.args.get("per_page", type=int)
    return redirect(
        url_for(
            "main.user_dashboard",
            page=page,
            per_page=per_page,
            reference=request.form.get("reference", "").strip(),
            name=request.form.get("name", "").strip(),
            colour=request.form.get("colour", "").strip(),
            main_group_top=request.form.get("main_group_top", "").strip(),
            main_group=request.form.get("main_group", "").strip(),
            main_group_sub=request.form.get("main_group_sub", "").strip(),
            present=request.form.get("present", "").strip(),
            price_order=request.form.get("price_order", "").strip(),
            votes_only=request.form.get("votes_only", "").strip(),
            order_mode=request.form.get("order_mode", "").strip() or request.args.get("order_mode", "").strip(),
        )
    )


def _admin_redirect(active_tab: str | None = None):
    params = {}
    tab = active_tab or request.form.get("active_tab") or request.args.get("active_tab")
    if tab:
        params["active_tab"] = tab
    target = url_for("main.admin_dashboard", **params)
    return redirect(target)


def _attempt_phase_backup(phase_at_backup: str, target_phase: str, *, flash_success: bool = False) -> None:
    """Try to create a backup without bloquear el cambio de fase."""
    Config.set("last_backup_phase", phase_at_backup)
    Config.set("last_backup_target_phase", target_phase)
    try:
        create_phase_backup(phase_at_backup=phase_at_backup, target_phase=target_phase)
        if flash_success:
            flash(f"Backup creado para {phase_at_backup} → {target_phase}.", "success")
    except Exception as exc:  # noqa: BLE001
        write_backup_error_log(exc)
        flash(
            "No se pudo crear el backup automático. Inténtalo manualmente y descarga el log de error.",
            "danger",
        )


def get_current_phase() -> str:
    value = get_campaign_phase()
    _auto_advance_phase_from_schedule(value)
    value = get_campaign_phase()
    return value if value in PHASES else "first"


def set_current_phase(phase: str, *, commit: bool = True) -> None:
    if phase not in PHASES:
        raise ValueError("Fase no válida")
    set_campaign_phase(phase, commit=commit)


def _ensure_admin():
    if not current_user.is_authenticated or not current_user.is_admin:
        abort(403)


def _bool_from_form(field_name: str = "state") -> bool:
    raw_value = request.form.get(field_name, "")
    return str(raw_value).lower() in {"1", "true", "on", "yes"}


def _handle_users_csv_upload(*, draft_campaign_id=None):
    file = request.files.get("csv_file")
    if not file or not file.filename:
        flash("Selecciona un archivo CSV válido.", "warning")
        return None

    try:
        decoded = file.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        flash("No se pudo leer el archivo: usa codificación UTF-8.", "danger")
        return None

    if not decoded.strip():
        flash("El archivo CSV está vacío.", "warning")
        return None

    stream = io.StringIO(decoded)
    reader = csv.DictReader(stream)
    if not reader.fieldnames:
        flash("El CSV debe incluir una fila de cabecera.", "warning")
        return None

    reader.fieldnames = [(name or "").strip().lower() for name in reader.fieldnames]
    # A participant import is never an administrator-management operation.
    # Reject the entire file rather than silently treating privilege fields as data.
    if "is_admin" in reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
        flash("El CSV contiene columnas duplicadas o un campo reservado (is_admin).", "danger")
        return None
    required_columns = {"username", "password"}
    missing = required_columns - set(reader.fieldnames)
    if missing:
        flash(
            f"Faltan columnas obligatorias en el CSV: {', '.join(sorted(missing))}.",
            "danger",
        )
        return None

    string_fields = {
        "first_name": "first_name",
        "last_name": "last_name",
        "dni": "dni",
        "declaration": "declaration",
    }
    bool_fields = {
        "active": "active",
        "agreements": "agreements_accepted",
        "agreements_accepted": "agreements_accepted",
        "paid": "paid",
    }

    # Archived campaigns may coexist with the current one. Enrol only into
    # the operational campaign; never revive an archived campaign or a draft.
    from app.models import Campaign
    from app.services.active_campaign import current_campaign
    from app.services.campaign_participation import enroll_existing_user
    if draft_campaign_id is not None:
        # Recheck the target inside the POST: never allow archived/active writes.
        registered_campaign = Campaign.query.filter_by(id=draft_campaign_id, status='draft').one_or_none()
        if registered_campaign is None:
            abort(409, description="El borrador ya no está disponible")
        if Campaign.query.filter_by(status='legacy_active').first() is not None:
            abort(409, description="Archiva la campaña anterior antes de preparar el borrador")
    else:
        try:
            registered_campaign = current_campaign()
        except RuntimeError:
            abort(409, description="Ambiguous active campaigns")
        if registered_campaign is None and Campaign.query.first() is not None:
            abort(409, description="Activate a campaign before importing participants")

    created = updated = skipped = 0
    seen_usernames = set()
    accepted_usernames = set()
    errors = []
    total_rows = 0

    default_password = current_app.config.get("DEFAULT_USER_PASSWORD")
    if not default_password or len(default_password) < 12:
        abort(503, description="Set a secure DEFAULT_USER_PASSWORD before importing participants")

    for row in reader:
        total_rows += 1
        line_no = reader.line_num
        row = {key: (value or "").strip() for key, value in row.items()}
        username = row.get("username", "")
        if not username:
            skipped += 1
            errors.append(f"Línea {line_no}: falta el username.")
            continue

        if username.casefold() in seen_usernames:
            skipped += 1
            errors.append(f"Línea {line_no}: usuario duplicado en el CSV.")
            continue
        seen_usernames.add(username.casefold())
        user = User.query.filter_by(username=username).first()
        if user and user.is_admin:
            skipped += 1
            errors.append(f"Línea {line_no}: una importación de participantes no puede editar administradores.")
            continue
        raw_password = row.get("password") or default_password
        is_new = False
        if not user:
            user = User(username=username, active=True)
            db.session.add(user)
            is_new = True
            user.set_password(raw_password)
            user.must_change_password = True
            user.declaration_file = None
            user.declaration_validated = False

        # User is a durable login identity: never overwrite its password,
        # account flags, signed-document state or old-year profile on re-enrolment.
        # The new year's approval is held exclusively in CampaignParticipation.
        if is_new:
            for csv_key, model_attr in string_fields.items():
                value = row.get(csv_key)
                if value:
                    setattr(user, model_attr, value)
            for csv_key, model_attr in bool_fields.items():
                if csv_key not in row:
                    continue
                parsed = _parse_bool(row.get(csv_key))
                if parsed is not None:
                    setattr(user, model_attr, parsed)
            created += 1
        else:
            updated += 1  # Existing identity enrolled, not overwritten.
        accepted_usernames.add(username.casefold())

    if created or updated:
        try:
            if registered_campaign is not None:
                # Flush creates ids for newly added identities; the whole
                # operation remains one transaction and can be rolled back.
                db.session.flush()
                for username in accepted_usernames:
                    user = User.query.filter(db.func.lower(User.username) == username).first()
                    if user is not None and not user.is_admin:
                        enroll_existing_user(registered_campaign.id, user.id)
            db.session.commit()
        except SQLAlchemyError as exc:
            db.session.rollback()
            flash(
                f"Error al confirmar la importación: {exc.orig if hasattr(exc, 'orig') else exc}",
                "danger",
            )
            return None
        flash(
            f"Usuarios importados. Nuevos: {created}, actualizados: {updated}, omitidos: {skipped}.",
            "success",
        )
    else:
        db.session.rollback()
        flash("No se importó ningún usuario.", "warning")

    return {
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
        "total": total_rows,
    }


def _parse_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if not normalized:
        return None
    if normalized in {"1", "true", "yes", "si", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return None


def _normalize_header(value: str) -> str:
    import re  # local import to avoid overhead when not used

    normalized = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return normalized


def _first_value(row_data: Dict[str, object], keys):
    for key in keys:
        value = row_data.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _normalize_reference_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return ""
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        text = str(value)
        return text.rstrip("0").rstrip(".")
    text = str(value).strip()
    if not text:
        return ""
    if text.endswith(".0") and text.replace(".", "", 1).isdigit():
        text = text[:-2]
    if text.replace(",", "").isdigit():
        text = text.replace(",", "")
    return text


def _build_color_lookup() -> Dict[str, str | None]:
    mapping: Dict[str, str | None] = {}
    for entry in ColorMap.query.all():
        if not entry.lego_name:
            continue
        mapping[entry.lego_name.strip().lower()] = entry.bl_name
    return mapping


def _build_color_overview():
    rows = (
        db.session.query(Product.colour_id)
        .filter(Product.campaign_id == active_campaign_id())
        .filter(Product.colour_id.isnot(None))
        .filter(Product.colour_id != "")
        .distinct()
        .order_by(Product.colour_id.asc())
        .all()
    )
    color_names = [row[0] for row in rows]
    mapping = _build_color_lookup()
    overview = []
    for name in color_names:
        bl_name = mapping.get(name.strip().lower()) if name else None
        overview.append({"lego_name": name, "bl_name": bl_name})
    return overview


def _get_distinct_main_group_tops() -> List[str]:
    results = (
        db.session.query(Product.main_group_top)
        .filter(Product.campaign_id == active_campaign_id())
        .filter(Product.main_group_top.isnot(None))
        .filter(Product.main_group_top != "")
        .distinct()
        .order_by(Product.main_group_top.asc())
        .all()
    )
    return [row[0] for row in results]


def _get_distinct_main_groups() -> List[str]:
    results = (
        db.session.query(Product.main_group)
        .filter(Product.campaign_id == active_campaign_id())
        .filter(Product.main_group.isnot(None))
        .filter(Product.main_group != "")
        .distinct()
        .order_by(Product.main_group.asc())
        .all()
    )
    return [row[0] for row in results]


def _get_distinct_main_group_subs() -> List[str]:
    results = (
        db.session.query(Product.main_group_sub)
        .filter(Product.campaign_id == active_campaign_id())
        .filter(Product.main_group_sub.isnot(None))
        .filter(Product.main_group_sub != "")
        .distinct()
        .order_by(Product.main_group_sub.asc())
        .all()
    )
    return [row[0] for row in results]


def _get_distinct_colours() -> List[Dict[str, str]]:
    results = (
        db.session.query(Product.colour_id)
        .filter(Product.campaign_id == active_campaign_id())
        .filter(Product.colour_id.isnot(None))
        .filter(Product.colour_id != "")
        .distinct()
        .order_by(Product.colour_id.asc())
        .all()
    )
    mapping = _build_color_lookup()
    options = []
    for row in results:
        name = row[0]
        bl_name = mapping.get(name.strip().lower()) if name else None
        label = f"{name} / {bl_name}" if bl_name else f"{name} / -"
        options.append({"value": name, "label": label})
    return options


def _calculate_final_selected_total() -> float:
    total = (
        db.session.query(
            func.coalesce(
                func.sum(UserVote.quantity * func.coalesce(Product.price, 0)), 0
            )
        )
        .join(Product, Product.id == UserVote.product_id)
        .filter(UserVote.campaign_id == active_campaign_id(), Product.campaign_id == active_campaign_id())
        .filter(Product.final_selected.is_(True))
        .filter(Product.final_disabled.is_(False))
        .scalar()
    )
    return float(total or 0.0)


def _calculate_user_total_final_selected(user_id: int) -> float:
    total = (
        db.session.query(
            func.coalesce(
                func.sum(UserVote.quantity * func.coalesce(Product.price, 0)), 0
            )
        )
        .join(Product, Product.id == UserVote.product_id)
        .filter(UserVote.campaign_id == active_campaign_id(), Product.campaign_id == active_campaign_id())
        .filter(UserVote.user_id == user_id)
        .filter(Product.final_selected.is_(True))
        .filter(Product.final_disabled.is_(False))
        .scalar()
    )
    return float(total or 0.0)


def _calculate_user_total(user_id: int) -> float:
    total = (
        db.session.query(
            func.coalesce(
                func.sum(UserVote.quantity * func.coalesce(Product.price, 0)), 0
            )
        )
        .join(Product, Product.id == UserVote.product_id)
        .filter(UserVote.campaign_id == active_campaign_id(), Product.campaign_id == active_campaign_id())
        .filter(UserVote.user_id == user_id)
        .scalar()
    )
    return float(total or 0.0)


def _validate_quantity_for_product(price: float, quantity: int) -> tuple[bool, str]:
    """Compatibility adapter; rule implementation lives in one tested service."""
    from app.services.quantity_rules import validate_quantity
    return validate_quantity(price, quantity)


def _calculate_global_order_total() -> float:
    total = (
        db.session.query(
            func.coalesce(
                func.sum(UserVote.quantity * func.coalesce(Product.price, 0)), 0
            )
        )
        .join(Product, Product.id == UserVote.product_id)
        .filter(UserVote.campaign_id == active_campaign_id(), Product.campaign_id == active_campaign_id())
        .scalar()
    )
    return float(total or 0.0)


def _purge_current_cycle_data() -> None:
    """Intentionally disabled: annual data must never be deleted to start a year.

    The supported successor is creation of a separate Campaign with its own
    participants and operational records. Fail closed until that flow is ready.
    """
    abort(409, description="Annual purge is disabled to preserve campaign history.")


def _get_products_with_votes_or_locked() -> Set[int]:
    vote_ids = {
        row.product_id
        for row in db.session.query(UserVote.product_id).filter(UserVote.campaign_id == active_campaign_id()).distinct().all()
    }
    locked_ids = {
        row.id
        for row in db.session.query(Product.id)
        .filter(Product.campaign_id == active_campaign_id())
        .filter(
            or_(
                Product.is_locked.is_(True),
                Product.final_promoted.is_(True),
            )
        )
        .all()
    }
    return vote_ids | locked_ids


def _get_products_with_votes() -> Set[int]:
    return {
        row.product_id
        for row in db.session.query(UserVote.product_id).filter(UserVote.campaign_id == active_campaign_id()).distinct().all()
    }


def _reset_order_exports_state() -> None:
    folder = current_app.config.get("ORDER_EXPORT_FOLDER")
    file_keys = [
        "final_order_excel",
        "final_order_piece_pdf",
        "final_order_user_pdf",
    ]
    # Do not delete files here: older campaigns can refer to the same basename.
    # Clearing annual pointers preserves historical exports and avoids cross-year
    # deletion. File garbage collection requires a separate reference audit.
    for key in file_keys:
        set_annual_setting(key, "")
    set_annual_setting('final_order_generated_at', "")
    set_annual_setting('final_order_last_tax', "")
    set_annual_setting('final_order_last_shipping', "")
    set_annual_setting('final_order_generated_at', "")
    set_annual_setting('final_order_payment_iban', "")
    set_annual_setting('final_order_payment_due_date', "")


def _clear_declaration_files() -> None:
    folder = current_app.config.get("DECLARATION_UPLOAD_FOLDER")
    if not folder or not os.path.isdir(folder):
        return
    for filename in os.listdir(folder):
        path = os.path.join(folder, filename)
        try:
            if os.path.isfile(path):
                os.remove(path)
        except OSError:
            continue


def _order_is_finalized() -> bool:
    return bool(get_annual_setting('final_order_generated_at'))


def _auto_advance_phase_from_schedule(current_phase: str | None = None) -> None:
    """Advance only through the supported annual campaign phases.

    An unmet global minimum keeps the campaign in the second phase; it
    must not be silently converted into a finalized order.
    """
    phase = current_phase if current_phase in PHASES else get_campaign_phase()
    phase = phase if phase in PHASES else "first"
    if phase not in {"first", "second"}:
        return

    today = date.today()
    second_phase_date = _parse_iso_date(get_annual_setting("second_phase_date"))
    final_phase_date = _parse_iso_date(get_annual_setting("order_deadline"))
    minimum = float(get_annual_setting("limit_minimum_total") or current_app.config.get("MIN_TOTAL_ORDER_AMOUNT", 4800))

    target = phase
    if target == "first" and second_phase_date and today >= second_phase_date:
        target = "second"
    if target == "second" and final_phase_date and today >= final_phase_date:
        if _calculate_global_order_total() >= minimum:
            target = "final"
    if target != phase:
        set_campaign_phase(target)


def _safe_archive_name(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in (value or "").strip())
    return cleaned.strip("_") or "archivo"


def _parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _regenerate_order_exports_in_background(payment_iban: str | None, payment_due_date: str | None) -> None:
    app = current_app._get_current_object()

    def _runner() -> None:
        with app.app_context():
            try:
                summary = build_final_order_context()
                if not summary["products"]:
                    return
                tax_amount = _get_config_float("final_order_last_tax")
                shipping_amount = _get_config_float("final_order_last_shipping")
                files = generate_order_files(
                    summary,
                    tax_amount,
                    shipping_amount,
                    payment_iban,
                    payment_due_date,
                )
                set_annual_setting('final_order_excel', files["excel"])
                set_annual_setting('final_order_piece_pdf', files.get("piece_pdf") or files.get("piece"))
                set_annual_setting('final_order_user_pdf', files.get("user_pdf") or files.get("user"))
                set_annual_setting('final_order_generated_at', datetime.utcnow().isoformat())
            except Exception as exc:  # noqa: BLE001
                app.logger.exception("No se pudieron regenerar los archivos del pedido tras guardar los datos de pago: %s", exc)
            finally:
                db.session.remove()

    threading.Thread(target=_runner, name="order-payment-regeneration", daemon=True).start()


def _is_valid_iban(value: str) -> bool:
    compact = "".join(char for char in value.upper() if char.isalnum())
    if len(compact) < 15 or len(compact) > 34:
        return False
    if not compact[:2].isalpha() or not compact[2:4].isdigit():
        return False
    rearranged = compact[4:] + compact[:4]
    numeric = []
    for char in rearranged:
        if char.isdigit():
            numeric.append(char)
        elif char.isalpha():
            numeric.append(str(ord(char) - 55))
        else:
            return False
    remainder = 0
    for char in "".join(numeric):
        remainder = (remainder * 10 + int(char)) % 97
    return remainder == 1


def _handle_products_excel_upload(content: bytes | None = None):
    active_campaign_id()  # Fail before parsing or writing when no active year exists.
    if content is None:
        file = request.files.get("excel_file")
        if not file or not file.filename:
            flash("Selecciona un archivo Excel valido (.xlsx).", "warning")
            return None
        try:
            content = file.read()
        except Exception as exc:  # noqa: BLE001
            flash(f"No se pudo leer el Excel: {exc}", "danger")
            return None

    try:
        workbook = load_workbook(filename=io.BytesIO(content), data_only=True)
    except Exception as exc:  # noqa: BLE001
        flash(f"No se pudo leer el Excel: {exc}", "danger")
        return None

    sheet = workbook.active
    header_row = next(sheet.iter_rows(min_row=1, max_row=1, values_only=True), None)
    if not header_row:
        flash("El Excel debe incluir una fila de cabecera.", "warning")
        return None

    headers = []
    for header in header_row:
        headers.append(_normalize_header(str(header or "")))

    def _has_any(cols: set[str]) -> bool:
        return any(col in headers for col in cols)

    if not _has_any({"reference", "communication_number", "material"}):
        flash(
            "El Excel necesita una columna de referencia (Material o Communication number).",
            "danger",
        )
        return None

    if not _has_any({"name", "description"}):
        flash("El Excel necesita la columna Description (nombre de la pieza).", "danger")
        return None

    string_fields = {
        "image_url": "image_url",
        "colour_id": "colour_id",
        "color_id": "colour_id",
        "main_group_top": "main_group_top",
        "main_group": "main_group",
        "main_group_sub": "main_group_sub",
    }
    bool_fields = {
        "is_locked": "is_locked",
        "present_in_2024": "present_in_2024",
        "on_list_2024": "present_in_2024",
        "on_list_2025": "present_in_2025",
    }

    created = updated = skipped = 0
    errors = []
    total_rows = 0
    seen_references: set[str] = set()
    color_lookup = _build_color_lookup()

    for row in sheet.iter_rows(min_row=2, values_only=True):
        total_rows += 1
        row_data = {}
        for idx, value in enumerate(row):
            if idx >= len(headers):
                continue
            row_data[headers[idx]] = value

        material_code_raw = _first_value(row_data, ["material"])
        material_code = _normalize_reference_value(material_code_raw)
        reference = material_code or _normalize_reference_value(
            _first_value(row_data, ["reference", "communication_number"])
        )
        if not reference:
            skipped += 1
            errors.append(f"Fila {total_rows + 1}: falta la referencia.")
            continue
        seen_references.add(reference)

        name_value = _first_value(row_data, ["name", "description", "descripcion", "descripci_n"])
        if not name_value:
            skipped += 1
            errors.append(f"Fila {total_rows + 1}: falta el nombre para {reference}.")
            continue

        product = products_query().filter_by(reference=reference).first()
        is_new = False
        if not product:
            product = Product(reference=reference, campaign_id=active_campaign_id())
            db.session.add(product)
            is_new = True

        product.name = name_value
        product.present_in_2025 = True

        for csv_key, attr in string_fields.items():
            value = row_data.get(csv_key)
            if value is not None and str(value).strip():
                setattr(product, attr, str(value).strip())

        image_value = row_data.get("image_url")
        if image_value and str(image_value).strip():
            product.image_url = str(image_value).strip()
        else:
            clean_material = (material_code or reference).replace(" ", "")
            product.image_url = (
                f"https://www.lego.com/cdn/product-assets/element.img.lod5photo.192x192/{clean_material}.jpg"
            )

        price_value = _first_value(row_data, ["2026_prices_in_eur", "2025_prices_in_eur", "price"])
        if price_value not in (None, ""):
            try:
                product.price = float(price_value)
            except (TypeError, ValueError):
                errors.append(
                    f"Fila {total_rows + 1}: precio inválido '{price_value}' para {reference}."
                )

        for csv_key, attr in bool_fields.items():
            if csv_key not in row_data:
                continue
            raw_value = row_data.get(csv_key)
            parsed = _parse_bool(None if raw_value in (None, "") else str(raw_value))
            if parsed is not None:
                setattr(product, attr, parsed)

        if product.colour_id:
            product.color_bl = color_lookup.get(product.colour_id.strip().lower())
        else:
            product.color_bl = None

        if is_new:
            created += 1
        else:
            updated += 1

    missing = 0
    missing_refs: list[str] = []
    if seen_references:
        missing_products = products_query().filter(~Product.reference.in_(seen_references)).all()
        missing = len(missing_products)
        for product in missing_products:
            if product.reference:
                missing_refs.append(str(product.reference))
            product.present_in_2025 = False
    else:
        flash("No se identificaron referencias válidas en el Excel; no se marcaron piezas fuera del listado.", "warning")

    try:
        db.session.commit()
    except SQLAlchemyError as exc:
        db.session.rollback()
        flash(
            f"Ocurrió un error al guardar las piezas: {exc.orig if hasattr(exc, 'orig') else exc}",
            "danger",
        )
        return None

    sample_refs = ", ".join(missing_refs[:10])
    sample_detail = f"Refs no presentes: {sample_refs}" if sample_refs else "Refs no presentes: 0"
    log_user_action(
        current_user.id,
        "excel_import",
        detail=(
            f"{current_user.username} cargo Excel. "
            f"Nuevas: {created}, actualizadas: {updated}, no presentes: {missing}, omitidas: {skipped}. "
            f"{sample_detail}"
        ),
        commit=True,
    )

    flash(
        f"Piezas importadas. Nuevas: {created}, actualizadas: {updated}, no presentes: {missing}, revisa incidencias para {skipped} filas omitidas.",
        "success",
    )

    return {
        "created": created,
        "updated": updated,
        "missing": missing,
        "skipped": skipped,
        "errors": errors,
        "total": total_rows,
    }


def _pending_catalog_matches(pending: dict, campaign_id: int, admin_id: int) -> bool:
    """Old session previews fail closed; never reuse an Excel across years/users."""
    return (
        isinstance(pending, dict)
        and type(pending.get("campaign_id")) is int
        and pending["campaign_id"] == campaign_id
        and type(pending.get("admin_id")) is int
        and pending["admin_id"] == admin_id
    )


def _save_pending_excel_upload(content: bytes) -> str:
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
    temp_file.write(content)
    temp_file.flush()
    temp_file.close()
    return temp_file.name


def _clear_pending_excel_upload() -> None:
    pending = session.pop("pending_excel_upload", None)
    if not pending:
        return
    path = pending.get("path")
    if path and os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


def _parse_products_excel(content: bytes):
    try:
        workbook = load_workbook(filename=io.BytesIO(content), data_only=True)
    except Exception as exc:  # noqa: BLE001
        return None, f"No se pudo leer el Excel: {exc}"

    sheet = workbook.active
    header_row = next(sheet.iter_rows(min_row=1, max_row=1, values_only=True), None)
    if not header_row:
        return None, "El Excel debe incluir una fila de cabecera."

    headers = []
    for header in header_row:
        headers.append(_normalize_header(str(header or "")))

    def _has_any(cols: set[str]) -> bool:
        return any(col in headers for col in cols)

    if not _has_any({"reference", "communication_number", "material"}):
        return None, "El Excel necesita una columna de referencia (Material o Communication number)."

    if not _has_any({"name", "description"}):
        return None, "El Excel necesita la columna Description (nombre de la pieza)."

    string_fields = {
        "image_url": "image_url",
        "colour_id": "colour_id",
        "color_id": "colour_id",
        "main_group_top": "main_group_top",
        "main_group": "main_group",
        "main_group_sub": "main_group_sub",
    }
    bool_fields = {
        "is_locked": "is_locked",
        "present_in_2024": "present_in_2024",
        "on_list_2024": "present_in_2024",
        "on_list_2025": "present_in_2025",
    }

    products: Dict[str, Dict[str, object]] = {}
    errors: list[str] = []
    total_rows = 0
    skipped = 0
    seen_normalized_references: set[str] = set()

    for row in sheet.iter_rows(min_row=2, values_only=True):
        total_rows += 1
        row_data = {}
        for idx, value in enumerate(row):
            if idx >= len(headers):
                continue
            row_data[headers[idx]] = value

        material_code_raw = _first_value(row_data, ["material"])
        material_code = _normalize_reference_value(material_code_raw)
        reference = material_code or _normalize_reference_value(
            _first_value(row_data, ["reference", "communication_number"])
        )
        if not reference:
            skipped += 1
            errors.append(f"Fila {total_rows + 1}: falta la referencia.")
            continue
        reference_key = reference
        normalized_reference = reference_key.strip().casefold()
        if normalized_reference in seen_normalized_references:
            skipped += 1
            errors.append(f"Fila {total_rows + 1}: referencia duplicada {reference_key}.")
            continue
        seen_normalized_references.add(normalized_reference)

        name_value = _first_value(row_data, ["name", "description", "descripcion", "descripci_n"])
        if not name_value:
            skipped += 1
            errors.append(f"Fila {total_rows + 1}: falta el nombre para {reference}.")
            continue

        data: Dict[str, object] = {
            "reference": reference_key,
            "name": name_value,
        }

        for csv_key, attr in string_fields.items():
            value = row_data.get(csv_key)
            if value is not None and str(value).strip():
                data[attr] = str(value).strip()

        image_value = row_data.get("image_url")
        if image_value and str(image_value).strip():
            data["image_url"] = str(image_value).strip()
        else:
            clean_material = (material_code or reference).replace(" ", "")
            data["image_url"] = (
                f"https://www.lego.com/cdn/product-assets/element.img.lod5photo.192x192/{clean_material}.jpg"
            )

        price_value = _first_value(row_data, ["2026_prices_in_eur", "2025_prices_in_eur", "price"])
        if price_value not in (None, ""):
            try:
                data["price"] = float(price_value)
            except (TypeError, ValueError):
                errors.append(
                    f"Fila {total_rows + 1}: precio invalido '{price_value}' para {reference}."
                )

        for csv_key, attr in bool_fields.items():
            if csv_key not in row_data:
                continue
            raw_value = row_data.get(csv_key)
            parsed = _parse_bool(None if raw_value in (None, "") else str(raw_value))
            if parsed is not None:
                data[attr] = parsed

        products[reference_key] = data

    return {
        "products": products,
        "errors": errors,
        "total": total_rows,
        "skipped": skipped,
    }, None


def _build_products_excel_preview(content: bytes):
    parsed, fatal_error = _parse_products_excel(content)
    if fatal_error:
        flash(fatal_error, "danger")
        return None

    existing_products = products_query().all()
    existing_by_ref = {product.reference: product for product in existing_products}
    new_by_ref = parsed["products"]

    added = []
    missing = []
    changed = []
    price_changed_refs = []

    for reference, data in new_by_ref.items():
        if reference not in existing_by_ref:
            added.append(data)
            continue

        product = existing_by_ref[reference]
        changes = []

        if data.get("name") != product.name:
            changes.append({
                "field": "Nombre",
                "old": product.name or "",
                "new": data.get("name") or "",
            })

        if "price" in data and data.get("price") != product.price:
            changes.append({
                "field": "Precio",
                "old": product.price,
                "new": data.get("price"),
            })
            price_changed_refs.append(reference)

        for field, label in (
            ("colour_id", "Color"),
            ("main_group_top", "Main group top"),
            ("main_group", "Main group"),
            ("main_group_sub", "Main group sub"),
            ("image_url", "Imagen"),
            ("is_locked", "Bloqueado"),
            ("present_in_2024", "Presente 2024"),
        ):
            if field in data and data.get(field) != getattr(product, field):
                changes.append({
                    "field": label,
                    "old": getattr(product, field),
                    "new": data.get(field),
                })

        if changes:
            changed.append({
                "reference": reference,
                "name": data.get("name") or product.name,
                "changes": changes,
            })

    for reference, product in existing_by_ref.items():
        if reference not in new_by_ref:
            missing.append({
                "reference": product.reference,
                "name": product.name,
                "price": product.price,
                "colour_id": product.colour_id,
                "main_group_top": product.main_group_top,
                "main_group": product.main_group,
                "main_group_sub": product.main_group_sub,
                "present_in_2024": product.present_in_2024,
                "is_locked": product.is_locked,
            })

    affected_orders = []
    missing_ids = [existing_by_ref[ref].id for ref in existing_by_ref if ref not in new_by_ref]
    if missing_ids:
        rows = (
            db.session.query(User.username, Product.reference, Product.name, Product.price, UserVote.quantity)
            .join(UserVote, UserVote.user_id == User.id)
            .join(Product, Product.id == UserVote.product_id)
            .filter(UserVote.product_id.in_(missing_ids), UserVote.campaign_id == active_campaign_id(), Product.campaign_id == active_campaign_id())
            .all()
        )
        for row in rows:
            affected_orders.append({
                "username": row[0],
                "reference": row[1],
                "name": row[2],
                "reason": "Referencia no presente en el listado",
                "old_price": row[3],
                "new_price": None,
                "quantity": row[4],
            })

    if price_changed_refs:
        price_map = {ref: new_by_ref[ref].get("price") for ref in price_changed_refs}
        rows = (
            db.session.query(User.username, Product.reference, Product.name, Product.price, UserVote.quantity)
            .join(UserVote, UserVote.user_id == User.id)
            .join(Product, Product.id == UserVote.product_id)
            .filter(Product.reference.in_(price_changed_refs), UserVote.campaign_id == active_campaign_id(), Product.campaign_id == active_campaign_id())
            .all()
        )
        for row in rows:
            affected_orders.append({
                "username": row[0],
                "reference": row[1],
                "name": row[2],
                "reason": "Cambio de precio",
                "old_price": row[3],
                "new_price": price_map.get(row[1]),
                "quantity": row[4],
            })

    return {
        "added": added,
        "missing": missing,
        "changed": changed,
        "affected_orders": affected_orders,
        "errors": parsed["errors"],
        "total": parsed["total"],
        "skipped": parsed["skipped"],
    }


@main_bp.route('/admin/commitment', methods=['GET', 'POST'])
@login_required
def commitment_management():
    _ensure_admin()
    if request.method == 'POST':
        upload = request.files.get('commitment_pdf')
        if not upload or not upload.filename or not upload.filename.lower().endswith('.pdf'):
            abort(400, description='PDF required')
        if upload.stream.read(5) != b'%PDF-':
            abort(400, description='Invalid PDF header')
        upload.stream.seek(0)
        import uuid
        filename = 'template-' + uuid.uuid4().hex + '.pdf'
        folder = current_app.config['DECLARATION_UPLOAD_FOLDER']
        upload.save(os.path.join(folder, filename))
        set_annual_setting('commitment_pdf', filename)
        # Only this year's approvals are invalidated; historic enrollments stay intact.
        from app.models import CampaignParticipation
        from app.services.campaign_data import active_campaign_id
        members = CampaignParticipation.query.filter_by(campaign_id=active_campaign_id()).all()
        for member in members:
            member.status = 'pending_review' if member.signed_document else 'pending_commitment'
            member.document_approved_at = None
            member.document_approved_by = None
        log_user_action(current_user.id, 'commitment_changed', 'New template; approvals reset', commit=True)
        flash('Compromiso publicado; las validaciones anteriores quedan anuladas.', 'success')
        return redirect(url_for('main.commitment_management'))
    from app.models import CampaignParticipation
    from app.services.campaign_data import active_campaign_id
    pending = (User.query.join(CampaignParticipation, CampaignParticipation.user_id == User.id)
               .filter(CampaignParticipation.campaign_id == active_campaign_id(),
                       CampaignParticipation.status != 'approved', User.is_admin.is_(False))
               .order_by(User.username).all())
    documents = {member.user_id: member.signed_document for member in
                 CampaignParticipation.query.filter_by(campaign_id=active_campaign_id()).all()}
    return render_template('admin_commitment.html', pending=pending, documents=documents,
                           has_commitment=bool(get_annual_setting('commitment_pdf')))


@main_bp.route('/admin/audit', methods=['GET'])
@login_required
def audit_dashboard():
    _ensure_admin()
    page = max(1, request.args.get('page', 1, type=int))
    logs = ActionLog.query.order_by(ActionLog.created_at.desc()).paginate(page=page, per_page=50)
    return render_template('admin_audit.html', logs=logs)


@main_bp.route('/admin/settings/limits', methods=['GET', 'POST'])
@login_required
def manage_limits():
    """Edit basic campaign monetary and selection limits before closing orders."""
    _ensure_admin()
    from decimal import Decimal, InvalidOperation
    keys = ('minimum_total', 'phase_one_order_limit', 'final_selection_limit')
    if request.method == 'POST':
        if _order_is_finalized():
            abort(409, description='A closed order cannot change its limits')
        raw = {key: (request.form.get(key) or '').strip() for key in keys}
        try:
            minimum = Decimal(raw['minimum_total'])
            ceiling = Decimal(raw['phase_one_order_limit'])
            selected = int(raw['final_selection_limit'])
            if (not minimum.is_finite() or not ceiling.is_finite() or
                minimum <= 0 or ceiling <= 0 or not 1 <= selected <= 1000):
                raise ValueError('Out of range')
        except (InvalidOperation, ValueError):
            abort(400, description='Invalid limit values')
        set_annual_setting('limit_minimum_total', str(minimum))
        set_annual_setting('limit_phase_one_order_limit', str(ceiling))
        set_annual_setting('limit_final_selection_limit', str(selected))
        log_user_action(current_user.id, 'limits_changed', str(raw)[:245], commit=True)
        flash('Límites guardados.', 'success')
        return redirect(url_for('main.manage_limits'))
    return render_template('admin_limits.html',
      minimum_total=get_annual_setting('limit_minimum_total') or current_app.config['MIN_TOTAL_ORDER_AMOUNT'],
      max_per_person=get_annual_setting('limit_phase_one_order_limit') or current_app.config['PHASE_ONE_ORDER_LIMIT'],
      max_references=get_annual_setting('limit_final_selection_limit') or current_app.config['FINAL_SELECTION_LIMIT'])


@main_bp.route('/admin/campaigns', methods=['GET'], endpoint='campaign_registry')
@login_required
def campaign_registry():
    """Read-only yearly registry until operational tables are campaign-scoped."""
    _ensure_admin()
    from app.services.campaign_registry import list_campaigns
    return render_template('admin_campaigns.html', campaigns=list_campaigns())


@main_bp.route('/admin/campaigns/<int:campaign_id>/calendar', methods=['GET', 'POST'])
@login_required
def manage_campaign_calendar(campaign_id):
    """Configure dates for a single year; archived seasons remain read-only."""
    _ensure_admin()
    from app.models import Campaign
    from app.services.campaign_calendar import (
        CampaignCalendarError, configure_campaign_window, read_campaign_window,
    )
    campaign = db.session.get(Campaign, campaign_id)
    if campaign is None:
        abort(404)
    editable = campaign.status in ('draft', 'legacy_active')
    if request.method == 'POST':
        if not editable:
            abort(409, description='No se pueden modificar campañas finalizadas.')
        try:
            start = date.fromisoformat(request.form.get('start_date', ''))
            end = date.fromisoformat(request.form.get('end_date', ''))
            configure_campaign_window(campaign, start, end, commit=False)
            from app.services.activity_log import log_user_action
            log_user_action(current_user.id, 'campaign_calendar_changed',
                            f'Campaña {campaign.year}: {start.isoformat()} - {end.isoformat()}',
                            commit=False)
            db.session.commit()
        except (ValueError, CampaignCalendarError):
            db.session.rollback()
            abort(400, description='Fechas de campaña inválidas.')
        except Exception:
            db.session.rollback()
            raise
        flash('Calendario de campaña guardado.', 'success')
        return redirect(url_for('main.manage_campaign_calendar', campaign_id=campaign.id))
    try:
        window = read_campaign_window(campaign)
    except CampaignCalendarError:
        current_app.logger.exception('Calendario inconsistente para campaña %s', campaign.id)
        abort(409, description='Calendario de campaña inconsistente.')
    return render_template('admin_campaign_calendar.html', campaign=campaign,
                           window=window, editable=editable)


@main_bp.route('/admin/shortage', methods=['GET','POST'])
@login_required
def shortage_admin():
    _ensure_admin()
    from app.services import shortage
    from app.services.active_campaign import current_campaign
    campaign=current_campaign()
    if campaign is None:abort(409)
    if request.method=='POST':
        try:
            action=request.form.get('action')
            if action=='open':
                days=int(request.form.get('days','7'))
                shortage.open_window(current_user.id,days)
                flash('Aviso extraordinario publicado.', 'success')
            elif action=='cancel':
                if request.form.get('confirm') != 'CANCELAR':abort(400)
                shortage.cancel(current_user.id)
                flash('Pedido cancelado por insuficiencia.', 'warning')
            elif action=='check':
                shortage.reconcile()
            else:abort(400)
        except ValueError as exc:
            flash(str(exc),'danger')
        return redirect(url_for('main.shortage_admin'))
    row=shortage.window_for_active()
    total=shortage.order_total(campaign.id)
    minimum=shortage.minimum_total()
    return render_template('shortage_admin.html',window=row,total=total,minimum=minimum,
                           missing=max(Decimal('0'),minimum-total))


@main_bp.route('/shortage/acknowledge',methods=['POST'])
@login_required
def shortage_acknowledge():
    if current_user.is_admin:abort(403)
    from app.services import shortage
    if request.form.get('read')!='yes':abort(400)
    try:shortage.acknowledge(current_user.id)
    except ValueError:abort(409)
    return redirect(url_for('main.user_dashboard'))


@main_bp.route('/shortage/increase', methods=['GET', 'POST'])
@login_required
def shortage_increase():
    if current_user.is_admin:
        abort(403)
    from app.services import shortage
    from app.models import ShortageAcknowledgement
    row = shortage.window_for_active()
    if not row or row.status != 'open':
        abort(409)
    if request.method == 'POST':
        try:
            product_id = int(request.form.get('product_id', ''))
            quantity = int(request.form.get('quantity', ''))
            shortage.add_extra_order(current_user.id, product_id, quantity)
            flash('Cantidad adicional registrada.', 'success')
        except (ValueError, TypeError) as exc:
            flash(str(exc), 'danger')
        return redirect(url_for('main.shortage_increase'))
    has_ack = ShortageAcknowledgement.query.filter_by(window_id=row.id, user_id=current_user.id).first() is not None
    products = shortage.selected_products_for_extension(row.campaign_id) if has_ack else []
    return render_template('shortage_increase.html', window=row, acknowledged=has_ack,
        products=products, margin=shortage.user_margin(row.campaign_id, current_user.id))
