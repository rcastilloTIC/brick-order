"""Real SQLAlchemy + SQLite transactional regression tests (no Flask required)."""
import pytest
from sqlalchemy import create_engine, Column, Integer, String, Boolean, ForeignKey, select
from sqlalchemy.orm import DeclarativeBase, Session


class Base(DeclarativeBase):
    pass


class Campaign(Base):
    __tablename__ = "campaign_tx"
    id = Column(Integer, primary_key=True)
    phase = Column(String(20), nullable=False)


class Product(Base):
    __tablename__ = "product_tx"
    id = Column(Integer, primary_key=True)
    campaign_id = Column(Integer, ForeignKey("campaign_tx.id"), nullable=False)
    selected = Column(Boolean, nullable=False)


class Order(Base):
    __tablename__ = "order_tx"
    id = Column(Integer, primary_key=True)
    campaign_id = Column(Integer, ForeignKey("campaign_tx.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("product_tx.id"), nullable=False)
    quantity = Column(Integer, nullable=False)


@pytest.fixture
def engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'transactions.sqlite'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all([Campaign(id=1, phase="final"), Campaign(id=2, phase="order"),
                         Product(id=10, campaign_id=1, selected=False),
                         Product(id=20, campaign_id=2, selected=True),
                         Order(id=20, campaign_id=2, product_id=20, quantity=8)])
        session.commit()
    yield engine
    engine.dispose()


def snapshot(engine):
    # Fresh connection proves the changes were (or were not) durably persisted.
    with Session(engine) as session:
        return (session.get(Campaign, 1).phase,
                session.get(Product, 10).selected,
                [(o.campaign_id, o.product_id, o.quantity)
                 for o in session.scalars(select(Order).order_by(Order.id))])


@pytest.mark.parametrize("failure_point", ["selection", "orders", "phase"])
def test_sqlalchemy_rollback_is_durable_and_campaign_scoped(engine, failure_point):
    before = snapshot(engine)
    with pytest.raises(RuntimeError, match="injected"):
        with Session(engine) as session:
            with session.begin():
                session.get(Product, 10).selected = True
                session.flush()
                if failure_point == "selection":
                    raise RuntimeError("injected after selection")
                session.add(Order(campaign_id=1, product_id=10, quantity=5))
                session.flush()
                if failure_point == "orders":
                    raise RuntimeError("injected after orders")
                session.get(Campaign, 1).phase = "order"
                session.flush()
                raise RuntimeError("injected after phase")
    assert snapshot(engine) == before


def test_sqlalchemy_commit_is_durable_and_campaign_scoped(engine):
    with Session(engine) as session:
        with session.begin():
            session.get(Product, 10).selected = True
            session.add(Order(campaign_id=1, product_id=10, quantity=5))
            session.get(Campaign, 1).phase = "order"
    assert snapshot(engine) == ("order", True, [(2, 20, 8), (1, 10, 5)])
