"""Verify annual consent classification against SQLite, without Flask."""
import re
import sqlite3
from pathlib import Path


def test_consent_counts_are_scoped_to_draft_campaign():
    source = (Path(__file__).resolve().parents[1] / 'app/services/annual_readiness.py').read_text()
    match = re.search(r"consent = db\.session\.execute\(text\('''(.*?)'''\)", source, re.S)
    assert match, 'Annual consent SQL not found'
    conn = sqlite3.connect(':memory:')
    conn.execute('CREATE TABLE campaign_participation (campaign_id INTEGER, user_id INTEGER, status TEXT, signed_document TEXT)')
    conn.executemany('INSERT INTO campaign_participation VALUES (?, ?, ?, ?)', [
        (2026, 1, 'approved', 'signed-2026.pdf'),
        (2027, 1, 'approved', None),
        (2027, 2, 'approved', 'signed-2027.pdf'),
        (2027, 3, 'pending_commitment', 'draft.pdf'),
        (2027, 4, 'approved', '   '),
    ])
    assert conn.execute(match.group(1), {'campaign_id': 2027}).fetchone() == (1, 2)
    assert conn.execute(match.group(1), {'campaign_id': 2026}).fetchone() == (1, 0)
    assert conn.execute(match.group(1), {'campaign_id': 2028}).fetchone() == (None, None)
