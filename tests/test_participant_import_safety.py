"""Source-level guards for annual participant import (not integration tests)."""
from pathlib import Path

ROUTES = (Path(__file__).resolve().parents[1] / 'app/main/routes.py').read_text()


def test_participant_csv_cannot_grant_admin():
    section = ROUTES.split('def _handle_users_csv_upload(', 1)[1].split('\ndef ', 1)[0]
    assert '"is_admin": "is_admin"' not in section
    assert '"is_admin" in reader.fieldnames' in section
    assert 'if user is not None and not user.is_admin:' in section


def test_import_registers_participation_atomically():
    section = ROUTES.split('def _handle_users_csv_upload(', 1)[1].split('\ndef ', 1)[0]
    assert 'db.session.flush()' in section
    assert 'enroll_existing_user(registered_campaign.id, user.id)' in section
    assert section.index('enroll_existing_user(registered_campaign.id, user.id)') < section.index('db.session.commit()')


def test_duplicate_csv_users_are_skipped():
    section = ROUTES.split('def _handle_users_csv_upload(', 1)[1].split('\ndef ', 1)[0]
    assert 'seen_usernames' in section
    assert 'if username.casefold() in seen_usernames:' in section
    assert 'accepted_usernames.add(username.casefold())' in section
