import unittest
from datetime import datetime, timedelta
from app import db
from app.models import Product, Order, ShortageWindow, ShortageAcknowledgement, CampaignParticipation
from app.services.campaign_phase import set_campaign_phase
from app.services.campaign_settings import set_annual_setting
from app.services.shortage import open_window, add_extra_order
from test_v83_multi_campaign_auto import MultiCampaignAutomaticTests

class ExtraordinaryIncreaseTests(MultiCampaignAutomaticTests):
    def setUp(self):
        super().setUp()
        set_campaign_phase('order')
        set_annual_setting('limit_minimum_total', '4800')
        self.now = datetime(2026, 11, 1)
        self.window = open_window(1, 7, self.now)
        self.user_id = 15
        self.product = Product.query.filter_by(campaign_id=2).first()
        self.assertIsNotNone(self.product)
        self.product.final_selected = True
        self.product.final_disabled = False
        db.session.commit()

    def _accept(self):
        member=CampaignParticipation.query.filter_by(campaign_id=2,user_id=self.user_id).first()
        member.status='approved'
        member.signed_document=member.signed_document or 'test-document.pdf'
        db.session.add(ShortageAcknowledgement(window_id=self.window.id,user_id=self.user_id,accepted_at=self.now))
        db.session.commit()

    def test_requires_acknowledgement(self):
        with self.assertRaises(ValueError):
            add_extra_order(self.user_id,self.product.id,25,self.now)

    def test_rejects_expired_window(self):
        self._accept()
        with self.assertRaises(ValueError):
            add_extra_order(self.user_id,self.product.id,25,self.now+timedelta(days=8))

    def test_rejects_unselected_reference(self):
        self._accept()
        self.product.final_selected=False
        db.session.commit()
        with self.assertRaises(ValueError):
            add_extra_order(self.user_id,self.product.id,25,self.now)

    def test_rejects_invalid_quantities(self):
        self._accept()
        for qty in (0,-1,True):
            with self.subTest(quantity=qty),self.assertRaises(ValueError):
                add_extra_order(self.user_id,self.product.id,qty,self.now)

    def test_rejects_closed_window(self):
        self._accept()
        self.window.status='cancelled'
        db.session.commit()
        with self.assertRaises(ValueError):
            add_extra_order(self.user_id,self.product.id,25,self.now)

    def test_valid_increment_only_on_selected_product(self):
        self._accept()
        before=Order.query.filter_by(campaign_id=2,user_id=self.user_id,product_id=self.product.id).count()
        result=add_extra_order(self.user_id,self.product.id,25,self.now)
        self.assertGreater(result.quantity,0)
        self.assertEqual(Order.query.filter_by(campaign_id=2,user_id=self.user_id,product_id=self.product.id).count(),before+1)
