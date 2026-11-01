"""Safe, non-destructive registry for the single existing (legacy) campaign.

Never infer that a campaign registry alone isolates participants or orders.
That will require a dedicated migration and changes to ALL operational queries.
"""
from datetime import date

from sqlalchemy.exc import IntegrityError

from app import db
from app.models import Campaign


def list_campaigns():
    """Return registered campaigns without modifying operational records."""
    return Campaign.query.order_by(Campaign.year.desc()).all()


def register_current_campaign(year: int, title: str) -> Campaign:
    """Record the current legacy dataset; no reset, archival or activation.

    A second legacy campaign is refused because the pre-migration database
    cannot distinguish data from different years.
    """
    if isinstance(year, bool) or not isinstance(year, int) or not 2000 <= year <= 2200:
        raise ValueError('Invalid campaign year')
    title = str(title).strip()
    if not title or len(title) > 120:
        raise ValueError('Invalid campaign title')
    existing = Campaign.query.filter_by(year=year).first()
    if existing:
        return existing
    if Campaign.query.first():
        raise ValueError('Cannot register a second campaign before data isolation migration')
    record = Campaign(year=year, title=title, status='legacy_active')
    db.session.add(record)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise ValueError('Campaign registry was updated concurrently') from None
    return record


def create_next_campaign_draft(*, year: int, title: str, actor_id: int) -> Campaign:
    """Register a future year without activating it or copying historical data.

    The only permitted situation is a fully archived previous campaign and no
    existing draft. This does not authorize imports, voting, or ordering.
    """
    from app.services.activity_log import log_user_action
    if isinstance(year, bool) or not isinstance(year, int) or not 2000 <= year <= 2200:
        raise ValueError('El año debe ser un número entre 2000 y 2200.')
    title = str(title).strip()
    if not title or len(title) > 120:
        raise ValueError('El título debe tener entre 1 y 120 caracteres.')
    campaigns = Campaign.query.all()
    if not campaigns or any(c.status not in ('archived', 'closed') for c in campaigns):
        raise ValueError('Primero hay que archivar la campaña anterior; solo se permite un borrador.')
    if year <= max(c.year for c in campaigns):
        raise ValueError('El nuevo año debe ser posterior al último registrado.')
    record = Campaign(year=year, title=title, status='draft')
    db.session.add(record)
    try:
        db.session.flush()
        log_user_action(actor_id, 'admin_campaign_draft', f'Borrador {year} (id={record.id}) creado.')
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise ValueError('El año ya existe o se ha registrado simultáneamente.') from None
    except Exception:
        # An audit failure or a database commit failure must never leave a
        # pending draft insert that a later unrelated request could commit.
        db.session.rollback()
        raise
    return record
