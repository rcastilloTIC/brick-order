"""Real Flask-SQLAlchemy/SQLite integration tests for final-order materialization.

Run with the project dependencies installed. Missing dependencies are reported as
skipped rather than incorrectly presenting mocked tests as real integration.
"""
import pytest

pytest.importorskip("flask")
pytest.importorskip("flask_sqlalchemy")
pytest.importorskip("flask_login")
pytest.importorskip("flask_wtf")
pytest.importorskip("flask_limiter")

from flask import Flask
from app import db
from app.models import Campaign, Order, Product, User, UserVote
from app.services.order_materialization import (
    materialize_selected_commitments, assert_selected_commitments_materialized,
)


@pytest.fixture
def database(tmp_path):
    app = Flask(__name__)
    app.config.update(SQLALCHEMY_DATABASE_URI=f"sqlite:///{tmp_path / 'integration.db'}",
                      SQLALCHEMY_TRACK_MODIFICATIONS=False, TESTING=True,
                      SECRET_KEY="integration-test-only")
    db.init_app(app)
    with app.app_context():
        db.create_all()
        db.session.add_all([
            Campaign(id=1, year=2026, title="Active", status="legacy_active"),
            Campaign(id=2, year=2025, title="Archived", status="archived"),
            User(id=1, username="participant", password_hash="test"),
            Product(id=10, campaign_id=1, reference="selected", final_selected=True,
                    final_disabled=False, price=0.1),
            Product(id=11, campaign_id=1, reference="discarded", final_selected=False,
                    final_disabled=False, price=0.1),
            Product(id=20, campaign_id=2, reference="historical", final_selected=True,
                    final_disabled=False, price=0.1),
            UserVote(campaign_id=1, user_id=1, product_id=10, quantity=5),
            UserVote(campaign_id=1, user_id=1, product_id=11, quantity=9),
            UserVote(campaign_id=2, user_id=1, product_id=20, quantity=8),
            Order(campaign_id=1, user_id=1, product_id=10, quantity=2),
            Order(campaign_id=2, user_id=1, product_id=20, quantity=3),
        ])
        db.session.commit()
        yield
        db.session.remove()
        db.drop_all()


def test_materialization_idempotent_and_campaign_scoped(database):
    assert materialize_selected_commitments() == (1, 3)
    assert_selected_commitments_materialized()
    db.session.commit()
    assert materialize_selected_commitments() == (0, 0)
    db.session.commit()
    assert sum(o.quantity for o in Order.query.filter_by(campaign_id=1, product_id=10)) == 5
    assert Order.query.filter_by(campaign_id=1, product_id=11).count() == 0
    assert sum(o.quantity for o in Order.query.filter_by(campaign_id=2, product_id=20)) == 3
    assert UserVote.query.filter_by(campaign_id=1, product_id=11).one().quantity == 9


@pytest.mark.parametrize("failure_point", ["after_materialization", "after_phase_update"])
def test_rollback_restores_orders_and_phase(database, failure_point):
    from app.services.campaign_phase import get_campaign_phase, set_campaign_phase
    # Explicit initial phase; changes below must share the same transaction.
    set_campaign_phase("final")
    assert get_campaign_phase() == "final"
    try:
        materialize_selected_commitments()
        assert_selected_commitments_materialized()
        if failure_point == "after_materialization":
            raise RuntimeError("injected after orders")
        set_campaign_phase("order", commit=False)
        raise RuntimeError("injected after phase")
    except RuntimeError:
        db.session.rollback()
    db.session.expire_all()
    assert get_campaign_phase() == "final"
    assert sum(o.quantity for o in Order.query.filter_by(campaign_id=1, product_id=10)) == 2
    assert Order.query.filter_by(campaign_id=2, product_id=20).one().quantity == 3


def test_validation_failure_rolls_back_uncommitted_selection(database):
    product = db.session.get(Product, 10)
    product.final_selected = False
    db.session.flush()
    with pytest.raises(ValueError, match="seleccionadas"):
        materialize_selected_commitments()
    db.session.rollback()
    db.session.expire_all()
    assert db.session.get(Product, 10).final_selected is True
    assert Order.query.filter_by(campaign_id=1, product_id=10).one().quantity == 2


@pytest.mark.parametrize("failure_point", ["after_selection", "after_materialization", "after_phase"])
def test_full_selection_order_phase_transaction_rolls_back(database, failure_point):
    """Exercise actual ORM selection, order rows and phase in one transaction."""
    from app.services.campaign_phase import get_campaign_phase, set_campaign_phase
    from app.services.final_selection import compute_final_selection

    set_campaign_phase("final")
    selected_before = {p.id: p.final_selected for p in Product.query.filter_by(campaign_id=1)}
    orders_before = [(o.product_id, o.quantity) for o in Order.query.filter_by(campaign_id=1).order_by(Order.id)]

    try:
        # This writes selection flags but must NOT commit them independently.
        summary = compute_final_selection(limit=1, persist=True, commit=False)
        assert summary["selected_count"] == 1
        if failure_point == "after_selection":
            raise RuntimeError("injected after selection")
        materialize_selected_commitments()
        assert_selected_commitments_materialized()
        if failure_point == "after_materialization":
            raise RuntimeError("injected after materialization")
        set_campaign_phase("order", commit=False)
        raise RuntimeError("injected after phase")
    except RuntimeError:
        db.session.rollback()

    db.session.expire_all()
    assert get_campaign_phase() == "final"
    assert {p.id: p.final_selected for p in Product.query.filter_by(campaign_id=1)} == selected_before
    assert [(o.product_id, o.quantity) for o in Order.query.filter_by(campaign_id=1).order_by(Order.id)] == orders_before


def test_full_selection_order_phase_transaction_commits(database):
    from app.services.campaign_phase import get_campaign_phase, set_campaign_phase
    from app.services.final_selection import compute_final_selection

    set_campaign_phase("final")
    summary = compute_final_selection(limit=1, persist=True, commit=False)
    assert summary["selected_count"] == 1
    # A fresh final selection is calculated from votes: reference 11 (9 units)
    # outranks reference 10 (5 units). The previous test incorrectly assumed
    # the initial final_selected fixture flag would remain authoritative.
    assert Product.query.filter_by(id=11, campaign_id=1).one().final_selected is True
    assert Product.query.filter_by(id=10, campaign_id=1).one().final_selected is False
    assert materialize_selected_commitments() == (1, 9)
    assert_selected_commitments_materialized()
    set_campaign_phase("order", commit=False)
    db.session.commit()

    db.session.expire_all()
    assert get_campaign_phase() == "order"
    assert Product.query.filter_by(id=11, campaign_id=1).one().final_selected is True
    assert sum(o.quantity for o in Order.query.filter_by(campaign_id=1, product_id=11)) == 9
    # The no-longer-selected reference's preexisting Order row is not erased.
    assert sum(o.quantity for o in Order.query.filter_by(campaign_id=1, product_id=10)) == 2
    assert Order.query.filter_by(campaign_id=2, product_id=20).one().quantity == 3


@pytest.mark.parametrize("bad_status", ["draft", "legacy_active"])
def test_inconsistent_campaign_registry_blocks_materialization(database, bad_status):
    """Fail closed when a second active year or an active/draft overlap exists."""
    from werkzeug.exceptions import Conflict
    archived = db.session.get(Campaign, 2)
    archived.status = bad_status
    db.session.commit()
    before = [(o.campaign_id, o.product_id, o.quantity)
              for o in Order.query.order_by(Order.id).all()]
    with pytest.raises(Conflict):
        materialize_selected_commitments()
    db.session.rollback()
    assert [(o.campaign_id, o.product_id, o.quantity)
            for o in Order.query.order_by(Order.id).all()] == before


def test_committed_phase_is_isolated_from_archived_campaign(database):
    """The phase key is campaign-specific, never a global archived-year value."""
    from app.models import Config
    from app.services.campaign_phase import get_campaign_phase, phase_config_key, set_campaign_phase
    Config.set(phase_config_key(2), "order")
    set_campaign_phase("final")
    assert get_campaign_phase() == "final"
    assert Config.get(phase_config_key(2)) == "order"
    db.session.remove()
    assert get_campaign_phase() == "final"
    assert Config.get(phase_config_key(2)) == "order"
