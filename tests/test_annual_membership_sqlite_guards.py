"""SQLite boundary regression independent of Flask dependencies."""
import sqlite3
import unittest


class AnnualMembershipSqliteGuards(unittest.TestCase):
    def test_insert_and_update_require_same_year_membership(self):
        db = sqlite3.connect(':memory:')
        db.executescript('''CREATE TABLE campaign_participation (campaign_id INTEGER, user_id INTEGER);
        CREATE TABLE user_vote (id INTEGER PRIMARY KEY, campaign_id INTEGER, user_id INTEGER);
        INSERT INTO campaign_participation VALUES (2026, 7);
        CREATE TRIGGER bom_user_vote_annual_member_insert BEFORE INSERT ON user_vote
        WHEN NEW.campaign_id IS NOT NULL AND NOT EXISTS (
          SELECT 1 FROM campaign_participation cp WHERE cp.campaign_id = NEW.campaign_id
          AND cp.user_id = NEW.user_id)
        BEGIN SELECT RAISE(ABORT, 'Missing annual membership'); END;
        CREATE TRIGGER bom_user_vote_annual_member_update BEFORE UPDATE ON user_vote
        WHEN NEW.campaign_id IS NOT NULL AND NOT EXISTS (
          SELECT 1 FROM campaign_participation cp WHERE cp.campaign_id = NEW.campaign_id
          AND cp.user_id = NEW.user_id)
        BEGIN SELECT RAISE(ABORT, 'Missing annual membership'); END;
        INSERT INTO user_vote VALUES (1, 2026, 7);
        ''')
        with self.assertRaises(sqlite3.IntegrityError):
            db.execute('INSERT INTO user_vote VALUES (2, 2027, 7)')
        with self.assertRaises(sqlite3.IntegrityError):
            db.execute('UPDATE user_vote SET campaign_id=2027 WHERE id=1')
        self.assertEqual(db.execute('SELECT campaign_id FROM user_vote WHERE id=1').fetchone()[0], 2026)
        db.close()
