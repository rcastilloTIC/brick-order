"""Regresión de la revisión 2026-11-01 (solo Pública): salida de una campaña cancelada."""
from datetime import timedelta
from app.time_utils import utc_now

from app import db
from app.models import Campaign, ShortageWindow
from app.services.shortage import open_window, reconcile
from tests._v92_campaign_fixture import _V92CampaignFixture


class CancelledCampaignExitRegression(_V92CampaignFixture):
    def _cancel(self):
        self.advance_to_order_through_http()
        start = utc_now() - timedelta(days=3)
        open_window(actor_id=self.ADMIN_ID, days=1, now=start)
        self.assertEqual(reconcile(start + timedelta(days=2)), 'cancelled')

    def _status(self, campaign_id):
        db.session.expire_all()
        return db.session.get(Campaign, campaign_id).status

    def test_backup_still_allowed_after_cancellation(self):
        self._cancel()
        self.login_as(self.ADMIN_ID)
        self.assertEqual(self.client.post('/admin/backup/create').status_code, 302)
        # Other mutations remain frozen.
        self.assertEqual(self.client.post('/admin/campaign-draft', data={'year': '2027'}).status_code, 409)

    def test_wrong_confirmation_does_not_close(self):
        self._cancel()
        self.post_as(self.ADMIN_ID, '/admin/shortage', {'action': 'close_campaign', 'confirm': 'CERRAR 2025'})
        self.assertEqual(self._status(self.ACTIVE_CAMPAIGN_ID), 'legacy_active')

    def test_close_preserves_history_and_unblocks_next_draft(self):
        self._cancel()
        orders_before = self.current_orders()
        self.post_as(self.ADMIN_ID, '/admin/shortage', {'action': 'close_campaign', 'confirm': 'CERRAR 2026'})
        self.assertEqual(self._status(self.ACTIVE_CAMPAIGN_ID), 'closed')
        self.assertEqual(self.current_orders(), orders_before)
        self.assert_previous_year_unchanged()
        self.post_as(self.ADMIN_ID, '/admin/campaign-draft', {'year': '2027', 'title': 'Campana simulada 2027'})
        self.assertEqual(Campaign.query.filter_by(year=2027).one().status, 'draft')

    def test_cannot_close_an_open_window(self):
        self.advance_to_order_through_http()
        open_window(actor_id=self.ADMIN_ID, days=7)
        self.post_as(self.ADMIN_ID, '/admin/shortage', {'action': 'close_campaign', 'confirm': 'CERRAR 2026'})
        self.assertEqual(self._status(self.ACTIVE_CAMPAIGN_ID), 'legacy_active')
        self.assertEqual(ShortageWindow.query.one().status, 'open')
