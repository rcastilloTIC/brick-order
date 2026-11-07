"""Regresión de la revisión 2026-11-01: parches 4-12 y cuadro de mando (propuesta A).

Común a ambas ediciones; las comprobaciones exclusivas miran el fichero EDITION.
Solo datos ficticios en una base temporal (fixture V92).
"""
from pathlib import Path

from werkzeug.security import generate_password_hash

from app import db
from app.models import User
from app.services.campaign_settings import get_annual_setting, set_annual_setting
from app.services.mode import is_test_mode_enabled
from tests._v92_campaign_fixture import _V92CampaignFixture

ROOT = Path(__file__).resolve().parents[1]
EDITION = (ROOT / 'EDITION').read_text().strip()


class HardeningRegression(_V92CampaignFixture):
    def _html(self, path='/admin', user_id=None):
        self.login_as(user_id or self.ADMIN_ID)
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True)[:600])
        return response.get_data(as_text=True)

    # ---- 4. Modo de pruebas
    def test_test_mode_requires_first_phase_and_typed_confirmation(self):
        self.login_as(self.ADMIN_ID)
        self.client.post('/admin/test-mode', data={'enable': '1', 'confirm': 'si'})
        self.assertFalse(is_test_mode_enabled())
        self.client.post('/admin/test-mode', data={'enable': '1', 'confirm': 'MODO PRUEBAS'})
        self.assertTrue(is_test_mode_enabled())
        self.assertEqual(get_annual_setting('test_mode'), '1')  # annual, not global
        self.client.post('/admin/test-mode', data={'enable': '0'})
        self.assertFalse(is_test_mode_enabled())

    def test_test_mode_cannot_be_enabled_once_orders_exist(self):
        self.advance_to_order_through_http()
        self.login_as(self.ADMIN_ID)
        self.client.post('/admin/test-mode', data={'enable': '1', 'confirm': 'MODO PRUEBAS'})
        self.assertFalse(is_test_mode_enabled())

    # ---- 5. Cabeceras y SRI
    def test_security_headers_and_sri(self):
        self.login_as(self.ADMIN_ID)
        response = self.client.get('/admin')
        self.assertEqual(response.headers.get('X-Frame-Options'), 'DENY')
        self.assertEqual(response.headers.get('X-Content-Type-Options'), 'nosniff')
        self.assertIn("frame-ancestors 'none'", response.headers.get('Content-Security-Policy', ''))
        html = response.get_data(as_text=True)
        self.assertEqual(html.count('integrity="sha384-'), 2)

    # ---- 7 y 8. Autenticación
    def test_inactive_user_not_revealed_without_password(self):
        user = db.session.get(User, 2)
        user.password_hash = generate_password_hash('clave-correcta-123')
        user.active = False
        db.session.commit()
        self.client.post('/login', data={'username': user.username, 'password': 'incorrecta'})
        with self.client.session_transaction() as session:
            messages = [m for _, m in session.get('_flashes', [])]
        self.assertIn('Usuario o contraseña incorrectos', messages)
        self.assertNotIn('Usuario desactivado, contacta con el administrador.', messages)

    def test_logout_requires_post(self):
        self.login_as(1)
        self.assertEqual(self.client.get('/logout').status_code, 405)
        self.assertEqual(self.client.post('/logout').status_code, 302)

    def test_profile_password_change_requires_current_password(self):
        user = db.session.get(User, 1)
        user.password_hash = generate_password_hash('clave-actual-123')
        db.session.commit()
        self.login_as(1)
        self.client.post('/profile', data={'new_password': 'nueva-clave-456', 'confirm_password': 'nueva-clave-456',
                                           'current_password': 'otra'})
        db.session.expire_all()
        self.assertTrue(db.session.get(User, 1).check_password('clave-actual-123'))
        self.client.post('/profile', data={'new_password': 'nueva-clave-456', 'confirm_password': 'nueva-clave-456',
                                           'current_password': 'clave-actual-123'})
        db.session.expire_all()
        self.assertTrue(db.session.get(User, 1).check_password('nueva-clave-456'))

    def test_remember_cookie_follows_session_security(self):
        source = (ROOT / 'config.py').read_text()
        self.assertIn('REMEMBER_COOKIE_HTTPONLY = True', source)
        self.assertEqual(source.count('REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE'), 2)  # base + production

    # ---- 9, 10, 12. Arranque, imagen y dependencias
    def test_entrypoints_and_image_hygiene(self):
        run = (ROOT / 'run.py').read_text()
        self.assertLess(run.index('load_dotenv()'), run.index('from config import'))
        self.assertIn('from run import app', (ROOT / 'wsgi.py').read_text())
        ignored = set((ROOT / '.dockerignore').read_text().split())
        self.assertTrue({'uploads/', 'exports/', 'backups/', '*.zip', '*.xlsx'} <= ignored)
        requirements = [l for l in (ROOT / 'requirements.txt').read_text().splitlines()
                        if l and not l.startswith('#')]
        self.assertTrue(all('==' in l for l in requirements), requirements)
        self.assertFalse(any(l.lower().startswith('redis') for l in requirements))
        self.assertNotIn('libpq-dev', (ROOT / 'Dockerfile').read_text())
        self.assertIn('TRUSTED_PROXY_COUNT=1', (ROOT / '.env.example').read_text())

    def test_payment_update_regenerates_synchronously(self):
        set_annual_setting('limit_minimum_total', '310')
        self.advance_to_order_through_http()
        self.post_as(self.ADMIN_ID, '/admin/order/generate')
        before = get_annual_setting('final_order_generated_at')
        self.assertTrue(before)
        import time; time.sleep(1.1)  # export names carry a per-second timestamp
        self.post_as(self.ADMIN_ID, '/admin/order/payment-details',
                     {'payment_iban': 'ES9121000418450200051332', 'payment_due_date': '2099-12-31'})
        with self.client.session_transaction() as session:
            messages = [m for _, m in session.get('_flashes', [])]
        self.assertIn('Datos de pago guardados y archivos del pedido regenerados.', messages)
        self.assertNotEqual(get_annual_setting('final_order_generated_at'), before)

    # ---- Propuesta A
    def test_control_room_renders_in_every_phase(self):
        for route, phase in [(None, 'first'), ('/admin/phase/activate-second', 'second'),
                             ('/admin/phase/advance-final', 'final'), ('/admin/phase/advance-order', 'order')]:
            if route:
                self.post_as(self.ADMIN_ID, route)
            html = self._html()
            self.assertIn('Campaña 2026', html, phase)
            self.assertIn('aria-current="step"', html, phase)
            self.assertNotIn('Limpiar datos del año anterior', html, phase)
            self.assertNotIn('Restaurar fuerza la fase', html, phase)
            self.assertIn('data-vb-edition="%s"' % EDITION.lower(), html)
            self.assertEqual(html.count('>Cuadro de mando<'), 1, phase)  # no duplicated menu label
        self.assertIn('Para generar el pedido definitivo', html)
        self.assertIn('id="pedido-final"', html)

    def test_edition_modules_never_mix(self):
        self.advance_to_order_through_http()
        html = self._html()
        if EDITION == 'PUBLICA':
            self.assertIn('Plazo de pedido insuficiente', html)
            self.assertNotIn('Ampliación privada', html)
            self.assertNotIn('ampliacion-privada', html)
        else:
            self.assertIn('id="ampliacion-privada"', html)
            self.assertNotIn('Plazo de pedido insuficiente', html)
            self.assertNotIn('Pedido insuficiente', html)

    def test_participant_sees_edition_accent_but_no_admin_menu(self):
        html = self._html('/dashboard', user_id=1)
        self.assertIn('data-vb-edition="%s"' % EDITION.lower(), html)
        self.assertNotIn('Ranking y selección', html)  # admin-only menu
        self.assertNotIn('Copias y modo de pruebas', html)


class DashboardPolishRegression(_V92CampaignFixture):
    def test_activity_is_human_readable(self):
        self.advance_to_order_through_http()
        if EDITION == 'PUBLICA':
            from app.services.shortage import open_window
            open_window(actor_id=self.ADMIN_ID, days=7)
        self.login_as(self.ADMIN_ID)
        html = self.client.get('/admin').get_data(as_text=True)
        section = html.split('id="vbc-activity"', 1)[1].split('id="sistema"', 1)[0]
        self.assertNotIn('campaign=', section)
        if EDITION == 'PUBLICA':
            self.assertIn('Abre el plazo de pedido insuficiente', section)
            self.assertNotIn('shortage_open', section)
        else:
            self.assertNotIn('Pedido mínimo:', html.split('id="ampliacion-privada"', 1)[1].split('</section>', 1)[0])
