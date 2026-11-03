import unittest
from datetime import datetime,timedelta
from decimal import Decimal
from test_v83_multi_campaign_auto import MultiCampaignAutomaticTests
from app import db
from app.models import Campaign, Config, Order, Product, ShortageWindow, ShortageAcknowledgement
from app.services.campaign_phase import set_campaign_phase
from app.services.campaign_settings import set_annual_setting
from app.services.shortage import open_window, acknowledge, reconcile, cancel, user_margin

class ShortageTests(MultiCampaignAutomaticTests):
    def setUp(self):
        super().setUp()
        set_campaign_phase('order')
        set_annual_setting('limit_minimum_total','4800')

    def test_open_and_expire(self):
        now=datetime(2026,11,1)
        row=open_window(1,7,now)
        self.assertEqual(row.deadline_at,now+timedelta(days=7))
        self.assertEqual(reconcile(now+timedelta(days=6)),'open')
        self.assertEqual(reconcile(now+timedelta(days=8)),'cancelled')
        self.assertIsNone(reconcile(now+timedelta(days=9)))

    def test_reached_minimum_wins_at_deadline(self):
        now=datetime(2026,11,1)
        open_window(1,1,now)
        db.session.add(Order(campaign_id=2,user_id=15,product_id=1001,quantity=25000))
        db.session.commit()
        self.assertEqual(reconcile(now+timedelta(days=2)),'reached')

    def test_cannot_open_twice_or_on_success(self):
        open_window(1,5)
        with self.assertRaises(ValueError):open_window(1,5)

    def test_admin_cancel(self):
        row=cancel(1)
        self.assertEqual(row.status,'cancelled')
        with self.assertRaises(ValueError):cancel(1)

    def test_validation(self):
        for days in [0,31,True,-2]:
            with self.subTest(days=days),self.assertRaises(ValueError):open_window(1,days)

    def test_campaign_scope(self):
        open_window(1,5)
        from app.services.shortage import window_for_active
        for c in Campaign.query.all(): c.status='archived'
        db.session.add(Campaign(id=3,year=2027,title='2027',status='legacy_active'))
        db.session.flush()
        self.assertIsNone(window_for_active())
        self.assertEqual(ShortageWindow.query.count(),1)
