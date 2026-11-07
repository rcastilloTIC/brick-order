"""V88 integration contracts: only synthetic DB, never production."""
import threading
import unittest
from datetime import datetime
from decimal import Decimal
from app import db
from app.models import CampaignParticipation, Order, ShortageAcknowledgement, Product, User
from app.services.campaign_settings import set_annual_setting
from app.services.campaign_phase import set_campaign_phase
from app.services.shortage import open_window, add_extra_order, user_margin
from test_v83_multi_campaign_auto import MultiCampaignAutomaticTests

class V88ConcurrentBudgetTests(MultiCampaignAutomaticTests):
    def setUp(self):
        super().setUp()
        set_campaign_phase('order')
        set_annual_setting('limit_minimum_total','4800')
        set_annual_setting('limit_phase_one_order_limit','40')
        self.now = datetime(2026, 11, 1)
        self.window = open_window(15, 7, self.now)
        self.product = Product.query.filter_by(campaign_id=2,reference='REF-001').one()
        member = CampaignParticipation.query.filter_by(campaign_id=2,user_id=15).one()
        member.status='approved'
        member.signed_document='fictional-consent.pdf'
        db.session.add(ShortageAcknowledgement(window_id=self.window.id,user_id=15,accepted_at=self.now))
        db.session.commit()

    def test_concurrent_increases_never_exceed_budget(self):
        # 2026 voted commitment for member 15: 85 x 0.20 = 17 euros.
        # Each increment adds 15 euros. Both together would exceed 40 euros.
        product_id=self.product.id
        barrier=threading.Barrier(2)
        outcomes=[]
        lock=threading.Lock()
        def submit():
            with self.app.app_context():
                barrier.wait(timeout=15)
                try:
                    add_extra_order(15,product_id,75,self.now)
                    outcome='ok'
                except Exception as exc:
                    outcome=type(exc).__name__
                finally:
                    db.session.remove()
                with lock: outcomes.append(outcome)
        threads=[threading.Thread(target=submit) for _ in range(2)]
        for thread in threads:thread.start()
        for thread in threads:thread.join(timeout=25)
        self.assertFalse(any(t.is_alive() for t in threads),'Concurrent workers blocked')
        self.assertEqual(len(outcomes),2,outcomes)
        self.assertEqual(outcomes.count('ok'),1,outcomes)
        self.assertEqual(Order.query.filter_by(campaign_id=2,user_id=15).count(),1)
        self.assertGreaterEqual(user_margin(2,15), Decimal('0'))

    def test_failure_rolls_back_reserved_write_lock(self):
        with self.assertRaises(ValueError):
            add_extra_order(15,1099,75,self.now)
        result=add_extra_order(15,self.product.id,75,self.now)
        self.assertEqual(result.quantity,76)

    def test_invalid_user_does_not_record_an_order(self):
        with self.assertRaises(ValueError):
            add_extra_order(36,self.product.id,75,self.now)
        self.assertEqual(Order.query.filter_by(campaign_id=2,user_id=36).count(),0)

    def test_private_extension_tables_absent_from_public_metadata(self):
        names=set(db.metadata.tables)
        self.assertNotIn('extension_interest',names)
        self.assertNotIn('final_extension_interest',names)
