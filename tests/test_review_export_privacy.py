"""Regresión de la revisión 2026-11-01: privacidad del PDF por participante y ZIP por pieza.

Solo datos ficticios en una base temporal (fixture V92).
"""
import io
import zipfile

from app import db
from app.models import User
from app.services.campaign_settings import get_annual_setting, set_annual_setting
from app.services.order_exports import find_participant_pdf, participant_pdf_name
from tests._v92_campaign_fixture import _V92CampaignFixture


class ExportPrivacyRegression(_V92CampaignFixture):
    def _generate(self):
        set_annual_setting('limit_minimum_total', '310')
        self.advance_to_order_through_http()
        self.post_as(self.ADMIN_ID, '/admin/order/generate')
        self.assertTrue(get_annual_setting('final_order_generated_at'))

    def _user_zip(self):
        return self.export_dir / get_annual_setting('final_order_user_pdf')

    def test_colliding_usernames_get_their_own_pdf(self):
        # 'participante.1' and 'participante_1' sanitise to the same text.
        db.session.get(User, 2).username = 'participante.1'
        db.session.commit()
        self._generate()
        with zipfile.ZipFile(self._user_zip()) as bundle:
            names = bundle.namelist()
            self.assertEqual(len(names), len(set(names)), names)
            own = {uid: bundle.read(find_participant_pdf(names, uid)) for uid in (1, 2)}
        self.assertNotEqual(own[1], own[2])
        for uid in (1, 2):
            self.login_as(uid)
            response = self.client.get('/dashboard/order-pdf')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data, own[uid])
            response.close()

    def test_user_without_pdf_entry_gets_404_not_another_pdf(self):
        self._generate()
        # Rewrite the bundle without user 3's entry: lookup must fail closed.
        path = self._user_zip()
        with zipfile.ZipFile(path) as bundle:
            kept = {n: bundle.read(n) for n in bundle.namelist()
                    if not n.startswith('usuario_3_')}
        with zipfile.ZipFile(path, 'w') as bundle:
            for name, data in kept.items():
                bundle.writestr(name, data)
        self.login_as(3)
        self.assertEqual(self.client.get('/dashboard/order-pdf').status_code, 404)

    def test_entry_name_is_keyed_by_id(self):
        self.assertEqual(participant_pdf_name(7, 'ana.garcia'), 'usuario_7_ana_garcia.pdf')
        names = ['usuario_7_ana_garcia.pdf', 'usuario_70_x.pdf', 'pedido_por_usuario_imprimir_1.pdf']
        self.assertEqual(find_participant_pdf(names, 7), 'usuario_7_ana_garcia.pdf')
        self.assertIsNone(find_participant_pdf(names, 8))
        self.assertIsNone(find_participant_pdf(names + ['usuario_7_otro.pdf'], 7))

    def test_admin_can_download_both_bundles(self):
        self._generate()
        self.login_as(self.ADMIN_ID)
        for kind in ('excel', 'piece', 'user'):
            response = self.client.get(f'/admin/order/download/{kind}')
            self.assertEqual(response.status_code, 200, kind)
            data = response.data
            response.close()
            if kind != 'excel':
                with zipfile.ZipFile(io.BytesIO(data)) as bundle:
                    self.assertIsNone(bundle.testzip())
                    names = bundle.namelist()
                    self.assertEqual(len(names), len(set(names)))
