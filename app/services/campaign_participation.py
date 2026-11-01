"""Annual enrolment operations, deliberately separate from login identities.

Important: these methods are not a replacement for campaign-scoping votes,
orders and products. New-year activation remains disabled until that migration.
"""
from app.time_utils import utc_now

from sqlalchemy.exc import IntegrityError

from app import db
from app.models import Campaign, CampaignParticipation, User

VALID_STATUSES = frozenset({'pending_commitment', 'pending_review', 'approved', 'rejected'})


def participation_for(campaign_id: int, user_id: int):
    """Look up membership using *both* the campaign and user id."""
    return CampaignParticipation.query.filter_by(
        campaign_id=campaign_id, user_id=user_id
    ).one_or_none()


def enroll_existing_user(campaign_id: int, user_id: int):
    """Enrol an existing user; never inherit last year's approval.

    Does not activate a campaign or grant access to legacy endpoints.
    Caller must commit its transaction. Unique constraint prevents duplicates.
    """
    campaign = Campaign.query.filter_by(id=campaign_id).first()
    if campaign is None:
        raise ValueError('Unknown campaign')
    if campaign.status not in ('draft', 'legacy_active'):
        raise ValueError('Cannot enrol participants in a closed or archived campaign')
    user = User.query.filter_by(id=user_id).first()
    if user is None or user.is_admin:
        raise ValueError('Invalid participant')
    existing = participation_for(campaign_id, user_id)
    if existing:
        return existing
    entry = CampaignParticipation(campaign_id=campaign_id, user_id=user_id,
                                  status='pending_commitment')
    db.session.add(entry)
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        raise ValueError('Participant was enrolled concurrently') from None
    return entry



def _require_active_membership_campaign(entry):
    """Reject stale participation records before changing their approval state."""
    campaign = Campaign.query.filter_by(id=entry.campaign_id).first()
    if campaign is None or campaign.status != 'legacy_active':
        raise ValueError('Cannot modify participation in a non-active campaign')


def submit_signed_document(entry, stored_filename: str):
    """New upload invalidates any prior approval; file validation is caller's job."""
    _require_active_membership_campaign(entry)
    if not isinstance(stored_filename, str) or not stored_filename.strip():
        raise ValueError('Missing stored PDF')
    if entry.status not in VALID_STATUSES:
        raise ValueError('Invalid participation status')
    entry.signed_document = stored_filename
    entry.document_approved_at = None
    entry.document_approved_by = None
    entry.status = 'pending_review'


def review_signed_document(entry, admin: User, approve: bool):
    """Approval requires an admin and an uploaded document."""
    _require_active_membership_campaign(entry)
    if not admin.is_admin:
        raise PermissionError('Administrator required')
    if entry.status != 'pending_review' or not entry.signed_document:
        raise ValueError('No pending document')
    entry.status = 'approved' if approve else 'rejected'
    entry.document_approved_at = utc_now() if approve else None
    entry.document_approved_by = admin.id


def is_eligible(campaign_id: int, user_id: int) -> bool:
    """Never authorise based on a previous year's membership."""
    entry = participation_for(campaign_id, user_id)
    return bool(entry and entry.status == 'approved' and entry.signed_document)
