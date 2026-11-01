"""Read-only annual history: every aggregate is explicitly scoped by campaign ID.

This module deliberately does not enable new campaigns or any mutation of old data.
"""
from decimal import Decimal

from app import db
from app.models import Campaign, CampaignParticipation, Order, Product, UserVote


def _money(value):
    if value is None:
        return Decimal('0.00')
    return Decimal(str(value))


def archived_campaign_summaries():
    """Return archival totals with no global, cross-year order/vote aggregations."""
    campaigns = (Campaign.query.filter(Campaign.status.in_(['archived', 'closed']))
                 .order_by(Campaign.year.desc()).all())
    results = []
    for campaign in campaigns:
        campaign_id = campaign.id
        members = CampaignParticipation.query.filter_by(campaign_id=campaign_id).count()
        products = Product.query.filter_by(campaign_id=campaign_id).count()
        selected = Product.query.filter_by(
            campaign_id=campaign_id, final_selected=True, final_disabled=False
        ).count()
        votes = UserVote.query.filter_by(campaign_id=campaign_id).count()
        orders = Order.query.filter_by(campaign_id=campaign_id).count()
        # Both sides of the join need campaign filters: an incorrect foreign
        # key must not cause prices from another year's catalog to leak in.
        order_rows = (db.session.query(Order.quantity, Product.price)
                      .join(Product, Order.product_id == Product.id)
                      .filter(Order.campaign_id == campaign_id,
                              Product.campaign_id == campaign_id).all())
        invalid = any(price is None or quantity is None or quantity < 0
                      for quantity, price in order_rows)
        if len(order_rows) != orders or invalid:
            total_display = None
        else:
            total = sum((_money(price) * quantity for quantity, price in order_rows),
                        Decimal('0.00'))
            total_display = f"{total.quantize(Decimal('0.01')):.2f}"
        results.append({
            'year': campaign.year, 'title': campaign.title, 'status': campaign.status,
            'members': members, 'products': products, 'selected': selected,
            'votes': votes, 'orders': orders, 'total': total_display,
        })
    return results
