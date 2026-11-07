"""Regresión de la revisión 2026-11-01 (ronda 3b): transiciones automáticas por fechas.

Un cambio de fase por calendario debe tener los mismos efectos que el botón
(copia previa y selección final persistida) y, en Extended, la ampliación
abierta debe ser visible en el panel y tener salida manual.
"""
from datetime import date, timedelta
from pathlib import Path

from app.models import Config, Product
from app.services.campaign_phase import get_campaign_phase
from app.services.campaign_settings import set_annual_setting
from tests._v92_campaign_fixture import _V92CampaignFixture

ROOT = Path(__file__).resolve().parents[1]
EDITION = (ROOT / 'EDITION').read_text().strip()
PAST = (date.today() - timedelta(days=2)).isoformat()
FUTURE = (date.today() + timedelta(days=5)).isoformat()


class ScheduleTransitionRegression(_V92CampaignFixture):
    def _admin_html(self):
        self.login_as(self.ADMIN_ID)
        response = self.client.get('/admin')
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True)[:500])
        return response.get_data(as_text=True)

    def _selected_ids(self):
        return {p.id for p in Product.query.filter_by(campaign_id=self.ACTIVE_CAMPAIGN_ID, final_selected=True)}

    def test_automatic_entry_into_final_has_manual_side_effects(self):
        # Minimum reached and order deadline passed: the calendar moves to "final".
        set_annual_setting('limit_minimum_total', '300')
        set_annual_setting('second_phase_date', PAST)
        set_annual_setting('order_deadline', PAST)
        self.assertEqual(self._selected_ids(), set())
        self._admin_html()
        self.assertEqual(get_campaign_phase(), 'final')
        self.assertEqual(Config.get('last_backup_target_phase'), 'final')   # backup attempted first
        self.assertEqual(self._selected_ids(), {self.RED_ID, self.BLUE_ID})  # selection persisted
        # The visitor who triggered it never sees a backup message.
        with self.client.session_transaction() as session:
            self.assertFalse([m for _, m in session.get('_flashes', []) if 'backup' in m.lower()])


if EDITION == 'EXTENDED':
    from app.models import ExtensionInterest

    class OpenExtensionRegression(_V92CampaignFixture):
        def _get(self, path, user_id):
            self.login_as(user_id)
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, response.get_data(as_text=True)[:500])
            return response.get_data(as_text=True)

        def _enter_open_extension(self):
            # Below the minimum (335 < 360) with an open extension window.
            set_annual_setting('second_phase_date', PAST)
            set_annual_setting('extension_start_date', PAST)
            set_annual_setting('extension_end_date', FUTURE)
            html = self._get('/admin', self.ADMIN_ID)
            self.assertEqual(get_campaign_phase(), 'extension')
            return html

        def test_dashboard_shows_open_extension_and_manual_exit(self):
            html = self._enter_open_extension()
            self.assertIn('Ampliación abierta (actual)', html)
            self.assertIn('id="vbc-open-extension"', html)
            self.assertIn('Cerrar la ampliación abierta y pasar a selección final', html)
            self.post_as(self.ADMIN_ID, '/admin/phase/advance-final')
            self.assertEqual(get_campaign_phase(), 'final')
            self._get('/admin', self.ADMIN_ID)          # a later request must not revert it
            self.assertEqual(get_campaign_phase(), 'final')
            self.assertTrue(Product.query.filter_by(campaign_id=self.ACTIVE_CAMPAIGN_ID, final_selected=True).count())

        def test_participant_can_join_open_extension(self):
            self._enter_open_extension()
            self.assertEqual(self._get('/dashboard', 2).count('/extension/interest'), 1)
            self.post_as(2, '/extension/interest', {'state': '1'})
            record = ExtensionInterest.query.filter_by(campaign_id=self.ACTIVE_CAMPAIGN_ID, user_id=2).one()
            self.assertTrue(record.active)

        def test_window_end_moves_to_final_automatically(self):
            self._enter_open_extension()
            set_annual_setting('extension_end_date', PAST)
            self._get('/admin', self.ADMIN_ID)
            self.assertEqual(get_campaign_phase(), 'final')
            self.assertEqual(Config.get('last_backup_phase'), 'extension')

        def test_step_hidden_when_not_configured(self):
            html = self._get('/admin', self.ADMIN_ID)
            self.assertNotIn('Ampliación abierta', html)
