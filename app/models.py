# app/models.py

from app.time_utils import utc_now
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from . import db

class User(db.Model, UserMixin):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    first_name = db.Column(db.String(50))
    last_name = db.Column(db.String(50))
    dni = db.Column(db.String(15))
    age = db.Column(db.Integer)
    agreements_accepted = db.Column(db.Boolean, default=False)
    active = db.Column(db.Boolean, default=True)
    is_admin = db.Column(db.Boolean, default=False)
    declaration = db.Column(db.String(255))
    paid = db.Column(db.Boolean, default=False)
    must_change_password = db.Column(db.Boolean, default=True)
    declaration_file = db.Column(db.String(255))
    declaration_validated = db.Column(db.Boolean, default=False)
    orders = db.relationship('Order', back_populates='user', cascade='all, delete-orphan')
    votes = db.relationship('UserVote', back_populates='user', cascade='all, delete-orphan')
    favorites = db.relationship('UserFavorite', back_populates='user', cascade='all, delete-orphan')
    action_logs = db.relationship('ActionLog', back_populates='user', cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Product(db.Model):
    __tablename__ = 'product'
    id = db.Column(db.Integer, primary_key=True)
    # Nullable only during migration of a pre-campaign database; new writes must set it.
    campaign_id = db.Column(db.Integer, db.ForeignKey('campaign.id'), index=True, nullable=True)
    image_url = db.Column(db.String(255))
    reference = db.Column(db.String(100), nullable=False)
    name = db.Column(db.String(255))
    price = db.Column(db.Float, nullable=True)
    is_locked = db.Column(db.Boolean, default=False)
    colour_id = db.Column(db.String(50))
    color_bl = db.Column(db.String(255))
    present_in_2024 = db.Column(db.Boolean, default=False)
    main_group_top = db.Column(db.String(100))
    main_group = db.Column(db.String(100))
    main_group_sub = db.Column(db.String(100))
    present_in_2025 = db.Column(db.Boolean, default=True)
    final_selected = db.Column(db.Boolean, default=False)
    final_disabled = db.Column(db.Boolean, default=False)
    final_promoted = db.Column(db.Boolean, default=False)
    orders = db.relationship('Order', back_populates='product', cascade='all, delete-orphan')
    votes = db.relationship('UserVote', back_populates='product', cascade='all, delete-orphan')
    favorites = db.relationship('UserFavorite', back_populates='product', cascade='all, delete-orphan')


class Order(db.Model):
    __tablename__ = 'order'
    id = db.Column(db.Integer, primary_key=True)
    # Nullable only during migration of a pre-campaign database; new writes must set it.
    campaign_id = db.Column(db.Integer, db.ForeignKey('campaign.id'), index=True, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    timestamp = db.Column(db.DateTime, default=utc_now)
    user = db.relationship('User', back_populates='orders')
    product = db.relationship('Product', back_populates='orders')


class ActionLog(db.Model):
    __tablename__ = 'action_log'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    action = db.Column(db.String(40), nullable=False)
    detail = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    user = db.relationship('User', back_populates='action_logs')


class ColorMap(db.Model):
    __tablename__ = 'color_map'
    id = db.Column(db.Integer, primary_key=True)
    lego_name = db.Column(db.String(100), unique=True, nullable=False)
    bl_name = db.Column(db.String(100))


class UserVote(db.Model):
    __tablename__ = 'user_vote'
    __table_args__ = (
        db.UniqueConstraint('user_id', 'product_id', name='uq_user_vote_product'),
    )
    id = db.Column(db.Integer, primary_key=True)
    # Nullable only during migration of a pre-campaign database; new writes must set it.
    campaign_id = db.Column(db.Integer, db.ForeignKey('campaign.id'), index=True, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    initial_quantity = db.Column(db.Integer, nullable=True)
    phase = db.Column(db.String(20), default='first')
    user = db.relationship('User', back_populates='votes')
    product = db.relationship('Product', back_populates='votes')


class UserFavorite(db.Model):
    __tablename__ = 'user_favorite'
    __table_args__ = (
        db.UniqueConstraint('user_id', 'product_id', name='uq_user_favorite_product'),
    )
    id = db.Column(db.Integer, primary_key=True)
    # Nullable only during migration of a pre-campaign database; new writes must set it.
    campaign_id = db.Column(db.Integer, db.ForeignKey('campaign.id'), index=True, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now)
    user = db.relationship('User', back_populates='favorites')
    product = db.relationship('Product', back_populates='favorites')


class Config(db.Model):
    __tablename__ = 'config'
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    value = db.Column(db.String(255), nullable=True)

    @staticmethod
    def get(key):
        entry = Config.query.filter_by(key=key).first()
        return entry.value if entry else None

    @staticmethod
    def set(key, value, *, commit=True):
        entry = Config.query.filter_by(key=key).first()
        if entry:
            entry.value = value
        else:
            entry = Config(key=key, value=value)
        db.session.add(entry)
        if commit:
            db.session.commit()






class CampaignParticipation(db.Model):
    """One person's enrolment in one annual campaign.

    Users are durable login identities; a participation is NOT. The same user
    may enrol in non-consecutive years. Consent and signed-document approval
    belong to this row, never to the user's lifetime identity.

    NOTE: legacy endpoints still use User.declaration_validated. Do not open
    registration for a second year until all those endpoints are migrated.
    """

    __tablename__ = 'campaign_participation'
    __table_args__ = (
        db.UniqueConstraint('campaign_id', 'user_id', name='uq_campaign_participation_user'),
    )
    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey('campaign.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default='pending_commitment')
    signed_document = db.Column(db.String(255), nullable=True)
    document_approved_at = db.Column(db.DateTime, nullable=True)
    document_approved_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    enrolled_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    user = db.relationship('User', foreign_keys=[user_id], backref='campaign_participations')
    campaign = db.relationship('Campaign', backref='participations')


class Campaign(db.Model):
    """Annual campaign registry. Data isolation is NOT enabled until every
    operational table has been migrated and every query is campaign-scoped.

    This intentionally does not provide a 'new campaign' operation: creating
    one with the existing global user/product tables would mix annual data.
    """

    __tablename__ = 'campaign'
    id = db.Column(db.Integer, primary_key=True)
    year = db.Column(db.Integer, unique=True, nullable=False)
    title = db.Column(db.String(120), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='legacy_active')
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    archived_at = db.Column(db.DateTime, nullable=True)



# Prevent deleting account/catalog parents while orders still reference them.
# Deleting either parent would otherwise cascade to historical Order rows.
# This is a safety net for ORM session.delete(), not a substitute for
# campaign-level authorization on every route or for database FK enforcement.
from sqlalchemy import event, select
from sqlalchemy.orm import Session


@event.listens_for(Session, 'before_flush')
def _protect_order_parents_from_deletion(session, flush_context, instances):
    deleted = tuple(session.deleted)
    for obj in deleted:
        if isinstance(obj, User) and obj.id is not None:
            exists = session.execute(
                select(Order.id).where(Order.user_id == obj.id).limit(1)
            ).first()
            if exists is not None:
                raise ValueError('Cannot delete a user with orders; retain historical ownership')
        if isinstance(obj, Product) and obj.id is not None:
            exists = session.execute(
                select(Order.id).where(Order.product_id == obj.id).limit(1)
            ).first()
            if exists is not None:
                raise ValueError('Cannot delete a product with orders; retain historical orders')


class CampaignInsightSnapshot(db.Model):
    """Observed campaign totals; captures only when an administrator views insights or runs capture CLI.

    Earlier history cannot be reconstructed from current UserVote rows.
    """
    __tablename__ = 'campaign_insight_snapshot'
    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey('campaign.id'), nullable=False, index=True)
    recorded_at = db.Column(db.DateTime, nullable=False, default=utc_now, index=True)
    vote_cents = db.Column(db.Integer, nullable=False)
    order_cents = db.Column(db.Integer, nullable=False)
    vote_units = db.Column(db.Integer, nullable=False)
    order_units = db.Column(db.Integer, nullable=False)
    voters = db.Column(db.Integer, nullable=False)
    buyers = db.Column(db.Integer, nullable=False)


class ShortageWindow(db.Model):
    """One shortage decision per annual campaign, separate from the campaign's lifecycle status."""
    __tablename__ = 'shortage_window'
    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey('campaign.id'), nullable=False, unique=True, index=True)
    status = db.Column(db.String(24), nullable=False)  # open, reached, cancelled
    opened_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    deadline_at = db.Column(db.DateTime, nullable=True)
    resolved_at = db.Column(db.DateTime, nullable=True)
    opened_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    closing_reason = db.Column(db.String(120), nullable=True)


class ShortageAcknowledgement(db.Model):
    __tablename__ = 'shortage_acknowledgement'
    __table_args__ = (db.UniqueConstraint('window_id', 'user_id', name='uq_shortage_ack_window_user'),)
    id = db.Column(db.Integer, primary_key=True)
    window_id = db.Column(db.Integer, db.ForeignKey('shortage_window.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    accepted_at = db.Column(db.DateTime, nullable=False, default=utc_now)
