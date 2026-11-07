"""PUBLIC V92: complete fictional season, through Flask/SQLite and real exports.

Run only in the disposable Docker runner: sh scripts/run_v92_e2e_isolated.sh
This edition tests the PUBLIC shortage notice and exceptional increases only.
"""
from datetime import timedelta
from app.time_utils import utc_now
from decimal import Decimal

from app import db
from app.models import Campaign, Order, ShortageWindow, ShortageAcknowledgement
from app.services.campaign_archive import CampaignArchiveError, archive_completed_campaign
from app.services.campaign_phase import set_campaign_phase
from app.services.shortage import add_extra_order, order_total, open_window, reconcile
from _v92_campaign_fixture import _V92CampaignFixture


class V92PublicCompleteCampaignE2E(_V92CampaignFixture):
    def test_complete_order_shortage_increase_excel_pdfs_archive_and_new_draft(self):
        # Real HTTP phase transitions compute final selection and transfer votes.
        self.advance_to_order_through_http()
        self.assertEqual(order_total(self.ACTIVE_CAMPAIGN_ID), self.BASE_TOTAL)

        # Missing 50 EUR: advertise the public notice to campaign members.
        self.post_as(self.ADMIN_ID, '/admin/shortage', {'action': 'open', 'days': '7'})
        window = ShortageWindow.query.filter_by(campaign_id=self.ACTIVE_CAMPAIGN_ID).one()
        self.assertEqual(window.status, 'open')
        self.assertIsNone(ShortageAcknowledgement.query.filter_by(user_id=1).first())

        # User cannot increase without confirming the public notice.
        self.post_as(1, '/shortage/increase', {'product_id': str(self.RED_ID),
                                              'quantity': '50'})
        self.assertEqual(order_total(self.ACTIVE_CAMPAIGN_ID), self.BASE_TOTAL)

        self.post_as(1, '/shortage/acknowledge', {'read': 'yes'})
        self.assertIsNotNone(ShortageAcknowledgement.query.filter_by(
            window_id=window.id, user_id=1).one_or_none())

        # A 1 EUR reference only accepts multiples of 25, not +10.
        self.post_as(1, '/shortage/increase', {'product_id': str(self.RED_ID),
                                              'quantity': '10'})
        self.assertEqual(order_total(self.ACTIVE_CAMPAIGN_ID), self.BASE_TOTAL)

        # Normal participant action: add 50 EUR in the public window.
        self.post_as(1, '/shortage/increase', {'product_id': str(self.RED_ID),
                                              'quantity': '50'})
        self.assertEqual(order_total(self.ACTIVE_CAMPAIGN_ID), self.FINAL_TOTAL)
        self.assert_final_order_consistent()
        self.assertEqual(reconcile(utc_now()), 'reached')
        db.session.expire_all()
        self.assertEqual(ShortageWindow.query.filter_by(
            campaign_id=self.ACTIVE_CAMPAIGN_ID).one().status, 'reached')

        # No additional public orders once the collective minimum was reached.
        self.login_as(1)
        response = self.client.post('/shortage/increase',
                                    data={'product_id': str(self.RED_ID), 'quantity': '25'})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(order_total(self.ACTIVE_CAMPAIGN_ID), self.FINAL_TOTAL)

        # Real XLSX, PDF and ZIP generation followed by fail-closed archival.
        excel = self.finalize_export_through_http()
        self.assert_tampering_rejected_then_archive(excel)

    def test_expired_public_notice_cancels_without_mutating_archived_orders(self):
        self.advance_to_order_through_http()
        start = utc_now() - timedelta(days=3)
        window = open_window(actor_id=self.ADMIN_ID, days=1, now=start)
        self.assertEqual(reconcile(start + timedelta(days=2)), 'cancelled')
        self.assertEqual(ShortageWindow.query.filter_by(id=window.id).one().status, 'cancelled')
        with self.assertRaises(ValueError):
            add_extra_order(user_id=1, product_id=self.RED_ID, quantity=50)
        db.session.rollback()
        self.assertEqual(order_total(self.ACTIVE_CAMPAIGN_ID), Decimal('310'))
        self.assert_previous_year_unchanged()
        with self.assertRaises(CampaignArchiveError):
            archive_completed_campaign(year=2026, export_folder=str(self.export_dir),
                                       actor_id=self.ADMIN_ID)
        self.assertEqual(db.session.get(Campaign, self.ACTIVE_CAMPAIGN_ID).status,
                         'legacy_active')
