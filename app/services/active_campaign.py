"""Single-active-campaign access policy during annual data migration.

Fail closed for multiple campaign records: the full order/vote isolation is not
ready, and mixing years would corrupt order ownership. No user can inherit a
signed-document approval from their lifetime identity once a campaign exists.
"""
from app.models import Campaign, CampaignParticipation


def current_campaign():
    """Resolve the one legacy-active campaign while excluding archived/draft years.

    A draft year is never operational. Do not permit a second active campaign;
    activation is intentionally blocked pending complete annual isolation.
    """
    campaigns = Campaign.query.all()
    # Never silently select an active year from a corrupt registry. A draft
    # cannot coexist with an operational campaign under the current policy.
    allowed = {'legacy_active', 'archived', 'closed', 'draft'}
    if any(c.status not in allowed for c in campaigns):
        raise RuntimeError('Unknown campaign status')
    active = [c for c in campaigns if c.status == 'legacy_active']
    drafts = [c for c in campaigns if c.status == 'draft']
    if len(active) > 1 or len(drafts) > 1 or (active and drafts):
        raise RuntimeError('Inconsistent campaign registry')
    return active[0] if active else None


def current_membership(user_id):
    campaign = current_campaign()
    if campaign is None:
        return None
    return CampaignParticipation.query.filter_by(campaign_id=campaign.id, user_id=user_id).one_or_none()


def allowed_to_participate(user_id):
    campaign = current_campaign()
    if campaign is None:
        return False  # Deny access until a campaign has been registered
    membership = CampaignParticipation.query.filter_by(campaign_id=campaign.id, user_id=user_id).one_or_none()
    return bool(membership and membership.status == 'approved' and membership.signed_document)


def require_campaign_participant(user_id: int, *, approved: bool = True) -> None:
    """Reject edits to an account outside the registered campaign.

    This guard must be called at the mutation boundary, including administrative
    edits, not just when a participant opens a page. It intentionally does not
    enable multiple concurrent/historical campaigns until all routes are scoped.
    """
    from flask import abort
    campaign = current_campaign()
    if campaign is None:
        abort(409, description="Debe registrar una campaña antes de modificar pedidos o votos.")
    membership = CampaignParticipation.query.filter_by(
        campaign_id=campaign.id, user_id=user_id
    ).one_or_none()
    if membership is None:
        abort(403, description="El usuario no participa en esta campaña.")
    if approved and (membership.status != "approved" or not membership.signed_document):
        abort(403, description="El compromiso de la campaña no está aprobado.")
