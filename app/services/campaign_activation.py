"""Explicit, transactional annual activation. Disabled unless explicitly enabled."""
import os
from sqlalchemy import text
from app import db
from app.models import Campaign, Config
from app.services.campaign_phase import phase_config_key


class CampaignActivationError(ValueError):
    pass


def activate_prepared_draft(*, year: int, actor_id: int, confirmation: str):
    """Promote a prepared draft without copying historical records.

    This is a deliberately opt-in release gate. An administrator must enable
    it only after validating all application routes and Docker integration.
    """
    if os.getenv('ENABLE_ANNUAL_ACTIVATION') != '1':
        raise CampaignActivationError('La activación anual no está habilitada en este despliegue.')
    if isinstance(year, bool) or not isinstance(year, int):
        raise CampaignActivationError('Año incorrecto.')
    if confirmation != f'ACTIVAR {year}':
        raise CampaignActivationError(f'Escribe ACTIVAR {year} para confirmar.')

    from app.services.annual_readiness import inspect_annual_readiness
    from app.services.activity_log import log_user_action
    campaigns = Campaign.query.all()
    drafts = [c for c in campaigns if c.status == 'draft']
    if len(drafts) != 1 or drafts[0].year != year:
        raise CampaignActivationError('Debe existir un único borrador para el año indicado.')
    if any(c.status not in ('archived', 'closed', 'draft') for c in campaigns):
        raise CampaignActivationError('Hay otra campaña operativa o un estado desconocido.')
    # A draft without an explicit season cannot be activated safely.
    # Check historical windows again at activation, not just on form save.
    from app.services.campaign_calendar import (
        read_campaign_window, other_campaign_windows,
        assert_no_window_overlap, CampaignCalendarError,
    )
    try:
        draft_window = read_campaign_window(drafts[0])
        if draft_window is None:
            raise CampaignCalendarError('El borrador necesita fechas de inicio y fin.')
        assert_no_window_overlap(*draft_window, other_campaign_windows(drafts[0].id))
    except CampaignCalendarError as exc:
        raise CampaignActivationError(str(exc)) from exc
    report = inspect_annual_readiness()
    preflight = report.get('draft_activation', {}).get(year)
    if not report.get('database_consistent') or not preflight or not preflight.get('data_prepared'):
        reasons = (preflight or {}).get('blockers', [])
        raise CampaignActivationError('Preparación incompleta: ' + '; '.join(reasons or report.get('findings', [])))

    # The new campaign must start at the first phase even when the archived
    # campaign ended at ordering. Do not call Config.set(): it commits itself
    # and would break the atomicity of activation + audit.
    draft = drafts[0]
    key = phase_config_key(draft.id)
    if Config.query.filter_by(key=key).first() is not None:
        raise CampaignActivationError('El borrador ya tiene una fase configurada; requiere revisión manual.')
    try:
        db.session.add(Config(key=key, value='first'))
        # Compare-and-swap in the database, not only the earlier ORM snapshot.
        # If another administrator changed the draft while preflight ran,
        # activation must fail without committing the phase or audit log.
        promoted = db.session.execute(text('''
            UPDATE campaign SET status = 'legacy_active'
            WHERE id = :campaign_id AND status = 'draft'
              AND NOT EXISTS (
                  SELECT 1 FROM campaign AS other
                  WHERE other.id != :campaign_id
                    AND other.status IN ('draft', 'legacy_active')
              )
        '''), {'campaign_id': draft.id})
        if promoted.rowcount != 1:
            raise CampaignActivationError(
                'El borrador cambió durante la activación; vuelve a comprobar el estado.')
        db.session.flush()
        log_user_action(actor_id, 'admin_campaign_activate',
                        f'Campaña {year} (id={draft.id}) activada; fase inicial first.')
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        if isinstance(exc, CampaignActivationError):
            raise
        raise CampaignActivationError(
            'No se pudo activar la campaña de forma atómica; revisa el estado.'
        ) from exc
    return draft
