"""Read-only campaign-scoped analytics. Votes are commitments, not paid orders."""
from decimal import Decimal, InvalidOperation
from datetime import timedelta
from app.time_utils import utc_now
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import func
from app import db
from app.models import Product, UserVote, Order, CampaignParticipation, Campaign, CampaignInsightSnapshot
from app.services.campaign_data import active_campaign_id


def _money(value):
    return round(float(value or 0), 2)


def _product_metrics(model, campaign_id, user_id=None):
    query = db.session.query(
        Product.id, Product.reference, Product.name, Product.colour_id,
        Product.main_group_top, Product.price,
        func.sum(model.quantity).label('pieces'),
        func.count(func.distinct(model.user_id)).label('participants'),
        func.sum(model.quantity * func.coalesce(Product.price, 0)).label('amount'),
    ).join(Product, Product.id == model.product_id).filter(
        model.campaign_id == campaign_id, Product.campaign_id == campaign_id
    )
    if user_id is not None:
        query = query.filter(model.user_id == user_id)
    return query.group_by(Product.id, Product.reference, Product.name,
                          Product.colour_id, Product.main_group_top, Product.price).all()


def _summarize(rows):
    return {
        'refs': len(rows),
        'pieces': sum(int(row.pieces or 0) for row in rows),
        'amount': _money(sum(Decimal(str(row.amount or 0)) for row in rows)),
    }


def _top(rows, limit=10):
    ordered = sorted(rows, key=lambda r: (-float(r.amount or 0), -int(r.pieces or 0), r.reference or ''))[:limit]
    peak = max((float(r.amount or 0) for r in ordered), default=0)
    return [{'reference': r.reference, 'name': r.name or r.reference,
             'pieces': int(r.pieces or 0), 'participants': int(r.participants or 0),
             'amount': _money(r.amount), 'width': round(100*float(r.amount or 0)/peak, 1) if peak else 0}
            for r in ordered]


def _groups(rows, key):
    totals = {}
    for row in rows:
        name = getattr(row, key) or 'Sin clasificar'
        totals[name] = totals.get(name, Decimal('0')) + Decimal(str(row.amount or 0))
    ordered = sorted(totals.items(), key=lambda x: (-x[1], x[0]))[:8]
    peak = max((value for _, value in ordered), default=Decimal('0'))
    return [{'label': label, 'amount': _money(value),
             'width': round(float(value / peak * 100), 1) if peak else 0} for label, value in ordered]


def build_insights(user_id=None):
    """Only currently active campaign; private per-user branch never exposes others."""
    campaign_id = active_campaign_id()
    vote_rows = _product_metrics(UserVote, campaign_id, user_id)
    order_rows = _product_metrics(Order, campaign_id, user_id)
    result = {
        'votes': _summarize(vote_rows),
        'orders': _summarize(order_rows),
        'top_votes': _top(vote_rows),
        'top_orders': _top(order_rows),
        'groups': _groups(vote_rows, 'main_group_top'),
        'colors': _groups(vote_rows, 'colour_id'),
        'personal': user_id is not None,
    }
    if user_id is None:
        counts = db.session.query(CampaignParticipation.status, func.count(CampaignParticipation.id)).filter(
            CampaignParticipation.campaign_id == campaign_id).group_by(CampaignParticipation.status).all()
        result['participants'] = dict(counts)
        result['participant_total'] = sum(int(n) for _, n in counts)
        result['voters'] = db.session.query(func.count(func.distinct(UserVote.user_id))).filter(
            UserVote.campaign_id == campaign_id).scalar() or 0
        result['buyers'] = db.session.query(func.count(func.distinct(Order.user_id))).filter(
            Order.campaign_id == campaign_id).scalar() or 0
        result['catalog_total'] = db.session.query(func.count(Product.id)).filter(
            Product.campaign_id == campaign_id).scalar() or 0
        # Provisional cutoff preview from current vote units (not an official selection).
        # Include zero-vote products; ties ordered by product ID for stable display.
        ranked = db.session.query(
            Product.id, Product.reference, Product.name,
            func.coalesce(func.sum(UserVote.quantity), 0).label('units'),
            func.count(func.distinct(UserVote.user_id)).label('people')
        ).outerjoin(UserVote, (UserVote.product_id == Product.id) &
                    (UserVote.campaign_id == campaign_id)).filter(
            Product.campaign_id == campaign_id
        ).group_by(Product.id, Product.reference, Product.name).all()
        ranked = sorted(ranked, key=lambda row: (-int(row.units), row.id))
        result['cutoff'] = {
            'available': len(ranked) > 85,
            'threshold': int(ranked[84].units) if len(ranked) >= 85 else 0,
            'nearby': [dict(position=pos, reference=row.reference,
                            name=row.name or row.reference,
                            units=int(row.units), people=int(row.people),
                            in_top=pos <= 85) for pos,row in enumerate(ranked, 1)
                       if 80 <= pos <= 90],
        }

        # Alert on units around provisional cutoff. Ties use same stable ID ordering.
        border = int(ranked[84].units) if len(ranked) >= 85 else 0
        result['cutoff']['alerts'] = [
            {'position': pos, 'reference': row.reference, 'units': int(row.units),
             'gap': max(0, border - int(row.units))}
            for pos, row in enumerate(ranked, 1)
            if len(ranked) > 85 and 83 <= pos <= 90
        ]
        raw_limit = None
        from app.services.campaign_settings import get_annual_setting
        raw_limit = get_annual_setting('limit_minimum_total')
        try:
            target = Decimal(str(raw_limit)) if raw_limit not in (None, '') else None
            if target is not None and (not target.is_finite() or target < 0):
                target = None
        except (InvalidOperation, TypeError, ValueError):
            target = None
        total = Decimal(str(result['orders']['amount']))
        result['budget'] = {
            'target': float(target) if target is not None else None,
            'current': float(total),
            'remaining': max(0.0, float(target - total)) if target is not None else None,
            'percentage': round(float(total / target * 100), 1) if target else None,
            'met': total >= target if target is not None else None,
        }
        result['history'] = load_snapshots(campaign_id)
        result['yearly'] = yearly_comparison(campaign_id, result)

    return result


def capture_snapshot(campaign_id, insights, *, now=None, minimum_minutes=30):
    """Persist actual observed figures; avoid one row per page refresh. Admin only caller.

    Same-minute changes are captured on next eligible observation (or CLI with 0).
    """
    now = now or utc_now()
    latest = (CampaignInsightSnapshot.query.filter_by(campaign_id=campaign_id)
              .order_by(CampaignInsightSnapshot.recorded_at.desc(), CampaignInsightSnapshot.id.desc()).first())
    current = (round(insights['votes']['amount'] * 100),
               round(insights['orders']['amount'] * 100),
               int(insights['votes']['pieces']), int(insights['orders']['pieces']),
               int(insights['voters']), int(insights['buyers']))
    if latest:
        old = (latest.vote_cents, latest.order_cents, latest.vote_units,
               latest.order_units, latest.voters, latest.buyers)
        if current == old or now - latest.recorded_at < timedelta(minutes=minimum_minutes):
            return False
    db.session.add(CampaignInsightSnapshot(campaign_id=campaign_id, recorded_at=now,
        vote_cents=current[0], order_cents=current[1], vote_units=current[2],
        order_units=current[3], voters=current[4], buyers=current[5]))
    db.session.commit()
    return True


def load_snapshots(campaign_id, *, limit=60):
    """Only real observations: no fake backfill or synthetic daily trend."""
    rows = (CampaignInsightSnapshot.query.filter_by(campaign_id=campaign_id)
            .order_by(CampaignInsightSnapshot.recorded_at.desc(), CampaignInsightSnapshot.id.desc())
            .limit(limit).all())
    rows.reverse()
    return [{'date': s.recorded_at.strftime('%d/%m %H:%M'),
             'votes': round(s.vote_cents / 100, 2), 'orders': round(s.order_cents / 100, 2),
             'vote_units': s.vote_units, 'order_units': s.order_units} for s in rows]


def yearly_comparison(active_id, insights):
    """Historical campaigns use last actual observation; otherwise show unavailable."""
    years = Campaign.query.order_by(Campaign.year.desc()).limit(12).all()
    data = []
    for year in years:
        if year.id == active_id:
            data.append({'year': year.year, 'status': year.status,
                         'votes': insights['votes']['amount'],
                         'orders': insights['orders']['amount'], 'observed': True, 'current': True})
            continue
        last = (CampaignInsightSnapshot.query.filter_by(campaign_id=year.id)
                .order_by(CampaignInsightSnapshot.recorded_at.desc(), CampaignInsightSnapshot.id.desc()).first())
        data.append({'year': year.year, 'status': year.status,
                     'votes': round(last.vote_cents / 100, 2) if last else None,
                     'orders': round(last.order_cents / 100, 2) if last else None,
                     'observed': bool(last), 'current': False})
    return data
