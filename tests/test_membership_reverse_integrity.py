"""Verify that removing or moving an annual enrolment cannot orphan history."""
import sqlite3
from pathlib import Path
import unittest


class MembershipReverseIntegrityTests(unittest.TestCase):
    def test_source_installs_both_reverse_guards(self):
        source = (Path(__file__).resolve().parents[1] / 'app' / '__init__.py').read_text()
        self.assertIn('bom_membership_delete_link_guard', source)
        self.assertIn('bom_membership_move_link_guard', source)
        self.assertIn('BEFORE DELETE ON campaign_participation', source)
        self.assertIn('BEFORE UPDATE OF campaign_id, user_id ON campaign_participation', source)

    def test_delete_move_rejected_and_other_year_remains_independent(self):
        db = sqlite3.connect(':memory:')
        db.executescript('''
            CREATE TABLE campaign_participation (id INTEGER PRIMARY KEY, campaign_id INTEGER, user_id INTEGER);
            CREATE TABLE "order" (campaign_id INTEGER, user_id INTEGER);
            CREATE TABLE user_vote (campaign_id INTEGER, user_id INTEGER);
            CREATE TABLE user_favorite (campaign_id INTEGER, user_id INTEGER);
            INSERT INTO campaign_participation VALUES (1,2026,7),(2,2027,7),(3,2026,8);
            INSERT INTO "order" VALUES (2026,7);
        ''')
        refs = ' OR '.join(
            f'EXISTS (SELECT 1 FROM "{table}" r WHERE r.campaign_id = OLD.campaign_id AND r.user_id = OLD.user_id)'
            for table in ('order','user_vote','user_favorite')
        )
        db.executescript(f'''
            CREATE TRIGGER bom_membership_delete_link_guard BEFORE DELETE ON campaign_participation
            WHEN {refs} BEGIN SELECT RAISE(ABORT, 'Annual membership has linked records'); END;
            CREATE TRIGGER bom_membership_move_link_guard BEFORE UPDATE OF campaign_id, user_id ON campaign_participation
            WHEN (NEW.campaign_id != OLD.campaign_id OR NEW.user_id != OLD.user_id) AND ({refs})
            BEGIN SELECT RAISE(ABORT, 'Annual membership has linked records'); END;
        ''')
        with self.assertRaises(sqlite3.IntegrityError):
            db.execute('DELETE FROM campaign_participation WHERE id=1')
        with self.assertRaises(sqlite3.IntegrityError):
            db.execute('UPDATE campaign_participation SET campaign_id=2027 WHERE id=1')
        with self.assertRaises(sqlite3.IntegrityError):
            db.execute('UPDATE campaign_participation SET user_id=8 WHERE id=1')
        db.execute('DELETE FROM campaign_participation WHERE id=2')
        self.assertEqual(db.execute('SELECT campaign_id,user_id FROM campaign_participation WHERE id=1').fetchone(), (2026,7))
        self.assertEqual(db.execute('SELECT COUNT(*) FROM "order"').fetchone()[0], 1)
        db.close()
