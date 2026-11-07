"""Automated multi-year isolation rehearsal. Never touches the production DB.

Run inside an isolated application image with:
 python -m unittest discover -s tests -p test_v83_multi_campaign_auto.py -v
"""
import tempfile
import unittest
from pathlib import Path
from flask import Flask
from werkzeug.exceptions import HTTPException
from app import db
from app.models import (Campaign, CampaignParticipation, User, Product,
                        UserVote, Order, UserFavorite, CampaignInsightSnapshot)
from app.services.active_campaign import (current_campaign, allowed_to_participate,
                                          require_campaign_participant)
from app.services.campaign_data import (active_campaign_id, products_query,
                                        orders_query, votes_query, favorites_query)
from app.services.order_materialization import (materialize_selected_commitments,
                                                assert_selected_commitments_materialized)
from app.services.order_insights import build_insights, load_snapshots


class MultiCampaignAutomaticTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='valbrick-v83-')
        self.app = Flask(__name__)
        self.app.config.update(SQLALCHEMY_DATABASE_URI='sqlite:///' + str(Path(self.temp.name)/'test.sqlite'),
                               SQLALCHEMY_TRACK_MODIFICATIONS=False, TESTING=True,
                               SECRET_KEY='only-for-automated-tests')
        db.init_app(self.app)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        db.session.add_all([
            Campaign(id=1, year=2025, title='Archived 2025', status='archived'),
            Campaign(id=2, year=2026, title='Current 2026', status='legacy_active'),
        ])
        for user_id in range(1, 41):
            db.session.add(User(id=user_id, username='fictional_%03d' % user_id,
                                password_hash='unusable-test-hash'))
            if user_id <= 25:
                db.session.add(CampaignParticipation(campaign_id=1, user_id=user_id,
                    status='approved', signed_document='fictional-2025.pdf'))
            if user_id in range(15, 36):
                db.session.add(CampaignParticipation(campaign_id=2, user_id=user_id,
                    status='approved' if user_id <= 30 else 'pending_commitment',
                    signed_document='fictional-2026.pdf' if user_id <= 30 else None))
        # Reuse reference names across years but never product IDs.
        for i in range(1, 101):
            db.session.add(Product(id=i, campaign_id=1, reference='REF-%03d' % i,
                                   final_selected=i<=85, final_disabled=False, price=0.15))
            db.session.add(Product(id=1000+i, campaign_id=2, reference='REF-%03d' % i,
                                   final_selected=i<=85, final_disabled=False, price=0.20))
        db.session.flush()
        for user_id in range(1, 26):
            for i in range(1, 11):
                db.session.add(UserVote(campaign_id=1,user_id=user_id,
                                        product_id=i,quantity=1+user_id%3))
        for user_id in range(15, 31):
            for i in range(1, 91):
                db.session.add(UserVote(campaign_id=2,user_id=user_id,
                                        product_id=1000+i,quantity=1+user_id%3))
            db.session.add(UserFavorite(campaign_id=2,user_id=user_id,product_id=1001))
        db.session.add(Order(campaign_id=1,user_id=1,product_id=1,quantity=8))
        db.session.add(CampaignInsightSnapshot(campaign_id=1,vote_cents=10000,
            order_cents=3000,vote_units=30,order_units=8,voters=25,buyers=1))
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()
        self.temp.cleanup()

    def test_archived_year_not_visible_in_current_queries(self):
        self.assertEqual(active_campaign_id(), 2)
        self.assertEqual(products_query().count(), 100)
        self.assertEqual(votes_query().count(), 16*90)
        self.assertEqual(orders_query().count(), 0)
        self.assertEqual(favorites_query().count(), 16)
        self.assertTrue(all(p.campaign_id==2 for p in products_query().all()))
        self.assertTrue(all(v.campaign_id==2 for v in votes_query().all()))

    def test_enrolment_does_not_inherit_previous_year(self):
        self.assertFalse(allowed_to_participate(1))   # Only in archived year
        self.assertTrue(allowed_to_participate(15))    # Approved in both years
        self.assertFalse(allowed_to_participate(31))  # Pending this year
        self.assertFalse(allowed_to_participate(36))  # No current membership
        for user_id in (1,31,36):
            with self.assertRaises(HTTPException):
                require_campaign_participant(user_id)
        require_campaign_participant(15)

    def test_selected_commitments_do_not_touch_archived_orders(self):
        previous = [(o.id,o.quantity) for o in Order.query.filter_by(campaign_id=1).all()]
        added, units = materialize_selected_commitments()
        self.assertEqual(added,16*85)
        self.assertGreater(units, 0)
        assert_selected_commitments_materialized()
        db.session.commit()
        self.assertEqual(previous,[(o.id,o.quantity) for o in Order.query.filter_by(campaign_id=1).all()])
        self.assertEqual(Order.query.filter_by(campaign_id=2).count(),16*85)
        # No orders for positions 86-90 (discarded votes).
        self.assertEqual(Order.query.filter(Order.campaign_id==2,Order.product_id>=1086).count(),0)
        self.assertEqual(materialize_selected_commitments(),(0,0))

    def test_private_insights_never_expose_other_users(self):
        personal=build_insights(user_id=15)
        all_users=build_insights()
        self.assertTrue(personal['personal'])
        self.assertFalse(all_users['personal'])
        self.assertLess(personal['votes']['pieces'],all_users['votes']['pieces'])
        self.assertEqual(personal['votes']['pieces'],90)
        self.assertEqual(personal['orders']['pieces'],0)
        self.assertEqual(all_users['voters'],16)
        self.assertEqual(all_users['catalog_total'],100)
        self.assertEqual(len(load_snapshots(2)),0)
        self.assertEqual(len(load_snapshots(1)),1)

    def test_second_active_campaign_is_blocked_not_silently_mixed(self):
        db.session.add(Campaign(id=3,year=2027,title='Invalid concurrent',status='legacy_active'))
        db.session.commit()
        with self.assertRaises(RuntimeError):
            current_campaign()
        with self.assertRaises(HTTPException) as cm:
            active_campaign_id()
        self.assertEqual(cm.exception.code,409)
        db.session.delete(db.session.get(Campaign,3))
        db.session.commit()
        self.assertEqual(active_campaign_id(),2)

    def test_future_draft_with_active_campaign_is_blocked(self):
        db.session.add(Campaign(id=3,year=2027,title='Blocked draft',status='draft'))
        db.session.commit()
        with self.assertRaises(RuntimeError):
            current_campaign()
        db.session.delete(db.session.get(Campaign,3))
        db.session.commit()


if __name__ == '__main__':
    unittest.main()
