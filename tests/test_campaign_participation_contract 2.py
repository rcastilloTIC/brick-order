"""Dependency-free regression checks for the safe annual membership design.

These are source/schema contract tests, not Flask integration tests.
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_annual_membership_has_unique_campaign_user_constraint():
    source = (ROOT / 'app/models.py').read_text()
    assert "class CampaignParticipation(db.Model):" in source
    assert "db.UniqueConstraint('campaign_id', 'user_id'" in source
    assert "db.ForeignKey('campaign.id')" in source
    assert "db.ForeignKey('user.id')" in source


def test_service_does_not_inherit_document_approval():
    source = (ROOT / 'app/services/campaign_participation.py').read_text()
    ast.parse(source)
    assert "status='pending_commitment'" in source
    assert "entry.document_approved_at = None" in source
    assert "entry.status == 'approved'" in source
    assert 'campaign_id=campaign_id, user_id=user_id' in source


def test_no_second_legacy_campaign():
    source = (ROOT / 'app/services/campaign_registry.py').read_text()
    assert 'Cannot register a second campaign before data isolation migration' in source
