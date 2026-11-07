"""Regresión (ronda 5): las páginas se cargan como lo haría un navegador.

El cambio de contraseña obligatorio daba error 500 en producción porque su
plantilla no existía, y ninguna prueba cargaba esa página con GET: solo
enviaban el formulario. Aquí se carga TODA página GET sin parámetros con tres
perfiles, y se comprueba estáticamente que no falten plantillas ni haya
formularios anidados (un <form> dentro de otro rompe el botón interior).
"""
import re
from pathlib import Path

from app import db
from app.models import CampaignParticipation, User
from tests._v92_campaign_fixture import _V92CampaignFixture

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / 'templates'


def test_every_referenced_template_exists():
    existing = {str(p.relative_to(TEMPLATES)) for p in TEMPLATES.rglob('*.html')}
    missing = []
    for py in list((ROOT / 'app').rglob('*.py')) + list((ROOT / 'orders').rglob('*.py')) + list((ROOT / 'products').rglob('*.py')):
        for name in re.findall(r"render_template\(\s*['\"]([^'\"]+)['\"]", py.read_text(encoding='utf-8')):
            if name not in existing:
                missing.append(f'{py.relative_to(ROOT)} -> {name}')
    for tpl in TEMPLATES.rglob('*.html'):
        for name in re.findall(r"\{%\s*(?:extends|include|import|from)\s+['\"]([^'\"]+)['\"]", tpl.read_text(encoding='utf-8')):
            if name not in existing:
                missing.append(f'{tpl.relative_to(ROOT)} -> {name}')
    assert missing == [], missing


def test_no_nested_forms():
    nested = []
    for tpl in TEMPLATES.rglob('*.html'):
        depth = 0
        for closing in re.findall(r'<(/?)form\b', tpl.read_text(encoding='utf-8')):
            depth += -1 if closing else 1
            if depth > 1:
                nested.append(str(tpl.relative_to(ROOT)))
    assert nested == [], nested


class PagesRenderLikeABrowser(_V92CampaignFixture):
    def setUp(self):
        super().setUp()
        # A real campaign publishes the commitment document before participants
        # arrive; without it /upload-declaration answers 503 on purpose.
        from app.services.campaign_settings import set_annual_setting
        set_annual_setting('commitment_pdf', 'compromiso-ensayo.pdf')
        folder = Path(self.app.config['DECLARATION_UPLOAD_FOLDER'])
        folder.mkdir(parents=True, exist_ok=True)
        (folder / 'compromiso-ensayo.pdf').write_bytes(b'%PDF-1.4\n%ensayo\n')

    def test_missing_commitment_file_is_not_a_server_error(self):
        (Path(self.app.config['DECLARATION_UPLOAD_FOLDER']) / 'compromiso-ensayo.pdf').unlink()
        self.login_as(1)
        response = self.client.get('/commitment/download')
        self.assertEqual(response.status_code, 503)
        response.close()

    def _get_routes(self):
        skip = {'static', 'auth.logout'}
        return sorted(rule.rule for rule in self.app.url_map.iter_rules()
                      if 'GET' in rule.methods and not rule.arguments and rule.endpoint not in skip)

    def _crawl(self, user_id):
        failures = []
        for path in self._get_routes():
            self.login_as(user_id)
            try:
                response = self.client.get(path)
            except Exception as exc:  # noqa: BLE001 - TESTING propagates server errors
                failures.append(f'{path}: {type(exc).__name__}: {exc}')
                continue
            if response.status_code >= 500:
                failures.append(f'{path}: HTTP {response.status_code}')
            response.close()
        return failures

    def test_admin_pages(self):
        self.assertEqual(self._crawl(self.ADMIN_ID), [])

    def test_approved_participant_pages(self):
        self.assertEqual(self._crawl(1), [])

    def test_newly_imported_participant_pages(self):
        user = db.session.get(User, 2)
        user.must_change_password = True
        membership = CampaignParticipation.query.filter_by(campaign_id=self.ACTIVE_CAMPAIGN_ID, user_id=2).one()
        membership.status, membership.signed_document = 'pending_commitment', None
        db.session.commit()
        self.assertEqual(self._crawl(2), [])

    def test_first_login_flow_as_a_browser(self):
        """Login -> forced password page (GET) -> change (POST) -> upload page (GET)."""
        from werkzeug.security import generate_password_hash
        user = db.session.get(User, 2)
        user.password_hash = generate_password_hash('Provisional-123')
        user.must_change_password = True
        membership = CampaignParticipation.query.filter_by(campaign_id=self.ACTIVE_CAMPAIGN_ID, user_id=2).one()
        membership.status, membership.signed_document = 'pending_commitment', None
        db.session.commit()
        client = self.app.test_client()
        response = client.post('/login', data={'username': user.username, 'password': 'Provisional-123'})
        self.assertTrue(response.headers['Location'].endswith('/change-password'))
        page = client.get('/change-password')
        self.assertEqual(page.status_code, 200)
        html = page.get_data(as_text=True)
        self.assertIn('name="new_password"', html)
        self.assertIn('name="confirm_password"', html)
        response = client.post('/change-password', data={'new_password': 'Propia-clave-456',
                                                         'confirm_password': 'Propia-clave-456'})
        self.assertTrue(response.headers['Location'].endswith('/upload-declaration'))
        self.assertEqual(client.get('/upload-declaration').status_code, 200)
        db.session.expire_all()
        self.assertFalse(db.session.get(User, 2).must_change_password)
