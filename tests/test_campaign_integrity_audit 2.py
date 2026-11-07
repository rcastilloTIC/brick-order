"""Real SQLite tests for the read-only annual-data integrity check."""
import importlib.util
import sqlite3
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / 'scripts' / 'audit_campaign_integrity.py'
spec = importlib.util.spec_from_file_location('audit_campaign_integrity', PATH)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def make_db(tmp_path):
    filename = tmp_path / 'campaign.sqlite'
    with sqlite3.connect(filename) as conn:
        conn.executescript('''
          CREATE TABLE campaign (id INTEGER PRIMARY KEY, status TEXT NOT NULL);
          CREATE TABLE user (id INTEGER PRIMARY KEY);
          CREATE TABLE campaign_participation (campaign_id INTEGER, user_id INTEGER);
          CREATE TABLE product (id INTEGER PRIMARY KEY, campaign_id INTEGER);
          CREATE TABLE "order" (id INTEGER PRIMARY KEY, campaign_id INTEGER, product_id INTEGER, user_id INTEGER);
          CREATE TABLE user_vote (id INTEGER PRIMARY KEY, campaign_id INTEGER, product_id INTEGER, user_id INTEGER);
          CREATE TABLE user_favorite (id INTEGER PRIMARY KEY, campaign_id INTEGER, product_id INTEGER, user_id INTEGER);
          INSERT INTO campaign VALUES (1, 'legacy_active');
          INSERT INTO user VALUES (1);
          INSERT INTO campaign_participation VALUES (1,1);
          INSERT INTO product VALUES (10,1);
          INSERT INTO user_vote VALUES (1,1,10,1);
        ''')
    return filename


def test_valid_single_campaign(tmp_path):
    assert audit.audit_database(make_db(tmp_path))['ok']


def test_reject_cross_campaign_vote(tmp_path):
    filename = make_db(tmp_path)
    with sqlite3.connect(filename) as conn:
        conn.execute('UPDATE user_vote SET campaign_id=2')
    result = audit.audit_database(filename)
    assert not result['ok']
    assert any('cross-campaign products' in x for x in result['issues'])


def test_reject_missing_product(tmp_path):
    filename = make_db(tmp_path)
    with sqlite3.connect(filename) as conn:
        conn.execute('UPDATE user_vote SET product_id=999')
    assert not audit.audit_database(filename)['ok']


def test_no_create_for_missing_database(tmp_path):
    filename = tmp_path / 'missing.sqlite'
    assert not audit.audit_database(filename)['ok']
    assert not filename.exists()


def test_reject_duplicate_membership(tmp_path):
    filename = make_db(tmp_path)
    with sqlite3.connect(filename) as conn:
        conn.execute('INSERT INTO campaign_participation VALUES (1,1)')
    assert any('duplicate memberships' in issue for issue in audit.audit_database(filename)['issues'])


def test_detect_order_from_user_not_enrolled(tmp_path):
    filename = make_db(tmp_path)
    with sqlite3.connect(filename) as conn:
        conn.execute('INSERT INTO user VALUES (2)')
        conn.execute('INSERT INTO "order" VALUES (1,1,10,2)')
    result = audit.audit_database(filename)
    assert not result['ok']
    assert any('not enrolled in that campaign' in issue for issue in result['issues'])

def test_detect_cross_campaign_owner(tmp_path):
    filename = make_db(tmp_path)
    with sqlite3.connect(filename) as conn:
        conn.execute('UPDATE user_vote SET user_id=2')
    result = audit.audit_database(filename)
    assert not result['ok']
    assert any('not enrolled in that campaign' in issue for issue in result['issues'])


def test_detect_duplicate_votes_within_campaign(tmp_path):
    filename = make_db(tmp_path)
    with sqlite3.connect(filename) as conn:
        conn.execute('INSERT INTO user_vote VALUES (2,1,10,1)')
    result = audit.audit_database(filename)
    assert not result['ok']
    assert any('duplicate user/product/campaign' in issue for issue in result['issues'])


def test_detect_nonpositive_quantities(tmp_path):
    filename = make_db(tmp_path)
    with sqlite3.connect(filename) as conn:
        conn.execute('ALTER TABLE user_vote ADD COLUMN quantity INTEGER')
        conn.execute('UPDATE user_vote SET quantity=0')
    result = audit.audit_database(filename)
    assert not result['ok']
    assert any('invalid quantities' in issue for issue in result['issues'])


def test_detect_duplicate_order_lines(tmp_path):
    filename = make_db(tmp_path)
    with sqlite3.connect(filename) as conn:
        conn.execute('INSERT INTO "order" VALUES (1,1,10,1)')
        conn.execute('INSERT INTO "order" VALUES (2,1,10,1)')
    report = audit.audit_database(filename)
    assert not report['ok']
    assert any('order:' in issue and 'duplicate' in issue for issue in report['issues'])


def test_detect_invalid_catalog_price(tmp_path):
    filename = make_db(tmp_path)
    with sqlite3.connect(filename) as conn:
        conn.execute('ALTER TABLE product ADD COLUMN price REAL')
        conn.execute('UPDATE product SET price=-1')
    report = audit.audit_database(filename)
    assert not report['ok']
    assert any('invalid or missing prices' in issue for issue in report['issues'])

def test_archived_campaign_and_clean_draft(tmp_path):
    filename = make_db(tmp_path)
    with sqlite3.connect(filename) as conn:
        conn.execute("UPDATE campaign SET status='archived'")
        conn.execute("INSERT INTO campaign (id, status) VALUES (2, 'draft')")
    assert audit.audit_database(filename)['ok']


def test_reject_records_in_draft(tmp_path):
    filename = make_db(tmp_path)
    with sqlite3.connect(filename) as conn:
        conn.execute("UPDATE campaign SET status='archived'")
        conn.execute("INSERT INTO campaign (id, status) VALUES (2, 'draft')")
        conn.execute('INSERT INTO product VALUES (11,2)')
    assert any('draft campaigns' in issue for issue in audit.audit_database(filename)['issues'])


def test_reject_two_active_campaigns(tmp_path):
    filename = make_db(tmp_path)
    with sqlite3.connect(filename) as conn:
        conn.execute("UPDATE campaign SET status='legacy_active'")
        conn.execute("INSERT INTO campaign (id, status) VALUES (2, 'legacy_active')")
    assert any('Multiple simultaneously active' in issue for issue in audit.audit_database(filename)['issues'])




def test_missing_campaign_lifecycle_column_is_not_reported_clean(tmp_path):
    filename = make_db(tmp_path)
    with sqlite3.connect(filename) as conn:
        conn.execute('ALTER TABLE campaign RENAME TO campaign_with_status')
        conn.execute('CREATE TABLE campaign (id INTEGER PRIMARY KEY)')
        conn.execute('INSERT INTO campaign (id) SELECT id FROM campaign_with_status')
        conn.execute('DROP TABLE campaign_with_status')
    report = audit.audit_database(filename)
    assert not report['ok']
    assert any('status column missing' in issue for issue in report['issues'])
