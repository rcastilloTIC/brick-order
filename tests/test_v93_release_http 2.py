"""Release gate: visible closing controls and guarded HTTP transitions (E2E)."""
import re

from app.models import Campaign
from app.services.campaign_phase import get_campaign_phase
from app.services.campaign_settings import get_annual_setting, set_annual_setting
from _v92_campaign_fixture import _V92CampaignFixture


def order_button_enabled(html):
    form = re.search(r'<form\b[^>]*action=["\']/admin/order/generate["\'][^>]*>(.*?)</form>',
                     html, re.S)
    if form is None:
        return None
    button = re.search(r'<button\b([^>]+)>\s*Realizar pedido\s*</button>', form.group(1), re.S)
    return bool(button) and not re.search(r'\bdisabled\b', button.group(1))


class V93ReleaseUIFlow(_V92CampaignFixture):
    def _admin_html(self):
        self.login_as(self.ADMIN_ID)
        response = self.client.get('/admin')
        self.assertEqual(response.status_code, 200,
                         response.get_data(as_text=True)[:700])
        return response.get_data(as_text=True)

    def test_export_button_activates_only_after_phase_is_released(self):
        self.post_as(self.ADMIN_ID, '/admin/phase/activate-second')
        self.post_as(self.ADMIN_ID, '/admin/phase/advance-final')
        self.assertEqual(get_campaign_phase(), 'final')
        set_annual_setting('limit_minimum_total', '310')
        # The form exists but must not be usable from the selection phase.
        self.assertFalse(order_button_enabled(self._admin_html()))
        self.post_as(self.ADMIN_ID, '/admin/order/generate')
        self.assertFalse(get_annual_setting('final_order_generated_at'))
        self.post_as(self.ADMIN_ID, '/admin/phase/advance-order')
        self.assertEqual(get_campaign_phase(), 'order')
        self.assertTrue(order_button_enabled(self._admin_html()))
        self.post_as(self.ADMIN_ID, '/admin/order/generate')
        self.assertTrue(get_annual_setting('final_order_generated_at'))
        # Not enough to generate: the admin must be able to archive afterwards.
        self.post_as(self.ADMIN_ID, '/admin/campaign-archive', {'confirm_year': '2026'})
        self.assertEqual(Campaign.query.filter_by(id=self.ACTIVE_CAMPAIGN_ID).one().status,
                         'archived')
        self.assert_previous_year_unchanged()

    def test_online_restore_is_rejected_without_mutation(self):
        self.advance_to_order_through_http()
        saved = dict(self.current_orders())
        self.login_as(self.ADMIN_ID)
        response = self.client.post('/admin/backup/restore')
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.current_orders(), saved)
