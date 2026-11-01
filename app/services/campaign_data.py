"""Campaign-scoped query helpers for product/order/vote data.

These helpers intentionally fail closed when there is no registered campaign.
New code should use these helpers, never an unscoped ``Model.query``.
They do not yet replace ALL legacy query sites. A second active year remains
blocked until a comprehensive route audit and data migration are complete.
"""
from flask import abort
from app.models import Order, Product, UserFavorite, UserVote
from app.services.active_campaign import current_campaign


def active_campaign_id():
    """Use the same fail-closed campaign policy as access controls."""
    try:
        campaign = current_campaign()
    except RuntimeError:
        abort(409, description="Multiple campaigns require completed annual isolation.")
    if campaign is None:
        abort(409, description="Register a campaign before accessing campaign data.")
    return campaign.id


def products_query():
    return Product.query.filter(Product.campaign_id == active_campaign_id())


def orders_query():
    return Order.query.filter(Order.campaign_id == active_campaign_id())


def votes_query():
    return UserVote.query.filter(UserVote.campaign_id == active_campaign_id())


def favorites_query():
    return UserFavorite.query.filter(UserFavorite.campaign_id == active_campaign_id())


def validate_product_campaign(product):
    """Prevent a foreign or unmigrated product from entering an annual order."""
    if product is None or product.campaign_id != active_campaign_id():
        abort(404)
    return product
