"""Shared *test-only* campaign fixture for the V92 Docker E2E rehearsals.

All data, declarations, backups and exports live in a freshly created
TemporaryDirectory.  No existing SQLite database or host directory is opened.
The actual Flask factory, SQLAlchemy models, HTTP routes and export writers
are exercised; these are not synthetic/mocked application services.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

from flask import g
from openpyxl import load_workbook

from app import create_app, db
from app.models import Campaign, CampaignParticipation, Config, Order, Product, User, UserVote
from app.services.active_campaign import current_campaign
from app.services.campaign_phase import get_campaign_phase
from app.services.campaign_settings import annual_key, get_annual_setting, set_annual_setting
from app.services.order_exports import build_final_order_context
from app.services.order_materialization import assert_selected_commitments_materialized, materialize_selected_commitments


class _V92CampaignFixture(unittest.TestCase):
    """A fictional 2026 campaign plus an immutable, older 2025 season."""

    ACTIVE_CAMPAIGN_ID = 10
    ARCHIVED_CAMPAIGN_ID = 9
    ADMIN_ID = 50
    RED_ID = 100
    BLUE_ID = 101
    REJECTED_ID = 102
    BASE_TOTAL = Decimal('310')
    FINAL_TOTAL = Decimal('360')

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='valbrick-v92-e2e-')
        self.root = Path(self.temporary.name)
        self.export_dir = self.root / 'exports'
        root = self.root

        class E2EConfig:
            TESTING = True
            SECRET_KEY = 'disposable-e2e-only-not-production'
            SQLALCHEMY_DATABASE_URI = 'sqlite:///' + str(root / 'scenario.sqlite')
            SQLALCHEMY_TRACK_MODIFICATIONS = False
            SITE_ACCESS_PASSWORD = None
            DECLARATION_UPLOAD_FOLDER = str(root / 'declarations')
            ORDER_EXPORT_FOLDER = str(root / 'exports')
            BACKUP_FOLDER = str(root / 'backups')
            TRUSTED_PROXY_COUNT = 0
            RATELIMIT_STORAGE_URI = 'memory://'
            WTF_CSRF_ENABLED = False
            DEFAULT_LANGUAGE = 'es'
            SUPPORTED_LANGUAGES = ('es', 'en')
            PHASE_ONE_ORDER_LIMIT = 550
            FINAL_SELECTION_LIMIT = 2

        self.app = create_app(E2EConfig)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        db.session.add_all([
            Campaign(id=self.ARCHIVED_CAMPAIGN_ID, year=2025,
                     title='Campana simulada 2025', status='archived'),
            Campaign(id=self.ACTIVE_CAMPAIGN_ID, year=2026,
                     title='Campana simulada 2026', status='legacy_active'),
            User(id=1, username='participante_1', password_hash='not-a-real-password',
                 active=True, is_admin=False, must_change_password=False),
            User(id=2, username='participante_2', password_hash='not-a-real-password',
                 active=True, is_admin=False, must_change_password=False),
            User(id=3, username='participante_3', password_hash='not-a-real-password',
                 active=True, is_admin=False, must_change_password=False),
            User(id=4, username='pendiente', password_hash='not-a-real-password',
                 active=True, is_admin=False, must_change_password=False),
            User(id=self.ADMIN_ID, username='administrador', password_hash='not-a-real-password',
                 active=True, is_admin=True, must_change_password=False),
        ])
        db.session.flush()
        db.session.add_all([
            CampaignParticipation(campaign_id=self.ARCHIVED_CAMPAIGN_ID,
                                  user_id=1, status='approved', signed_document='signed-2025.pdf'),
            CampaignParticipation(campaign_id=self.ACTIVE_CAMPAIGN_ID,
                                  user_id=1, status='approved', signed_document='signed-2026-1.pdf'),
            CampaignParticipation(campaign_id=self.ACTIVE_CAMPAIGN_ID,
                                  user_id=2, status='approved', signed_document='signed-2026-2.pdf'),
            CampaignParticipation(campaign_id=self.ACTIVE_CAMPAIGN_ID,
                                  user_id=3, status='approved', signed_document='signed-2026-3.pdf'),
            CampaignParticipation(campaign_id=self.ACTIVE_CAMPAIGN_ID,
                                  user_id=4, status='pending_commitment', signed_document=None),
            Product(id=90, campaign_id=self.ARCHIVED_CAMPAIGN_ID,
                    reference='LADRILLO-ROJO', name='Rojo ano anterior',
                    colour_id='5', price=1.0, final_selected=True),
            Product(id=self.RED_ID, campaign_id=self.ACTIVE_CAMPAIGN_ID,
                    reference='LADRILLO-ROJO', name='Ladrillo rojo', colour_id='5',
                    price=1.0, is_locked=True, final_selected=False, final_disabled=False),
            Product(id=self.BLUE_ID, campaign_id=self.ACTIVE_CAMPAIGN_ID,
                    reference='LADRILLO-AZUL', name='Ladrillo azul', colour_id='7',
                    price=2.0, is_locked=True, final_selected=False, final_disabled=False),
            Product(id=self.REJECTED_ID, campaign_id=self.ACTIVE_CAMPAIGN_ID,
                    reference='LADRILLO-VERDE', name='Ladrillo verde', colour_id='6',
                    price=0.5, final_selected=False, final_disabled=False),
        ])
        db.session.flush()
        db.session.add_all([
            UserVote(campaign_id=self.ARCHIVED_CAMPAIGN_ID, user_id=1,
                     product_id=90, quantity=25),
            Order(campaign_id=self.ARCHIVED_CAMPAIGN_ID, user_id=1,
                  product_id=90, quantity=25),
            UserVote(campaign_id=self.ACTIVE_CAMPAIGN_ID, user_id=1,
                     product_id=self.RED_ID, quantity=200),
            UserVote(campaign_id=self.ACTIVE_CAMPAIGN_ID, user_id=1,
                     product_id=self.BLUE_ID, quantity=20),
            UserVote(campaign_id=self.ACTIVE_CAMPAIGN_ID, user_id=2,
                     product_id=self.RED_ID, quantity=25),
            UserVote(campaign_id=self.ACTIVE_CAMPAIGN_ID, user_id=2,
                     product_id=self.BLUE_ID, quantity=10),
            UserVote(campaign_id=self.ACTIVE_CAMPAIGN_ID, user_id=3,
                     product_id=self.RED_ID, quantity=25),
            UserVote(campaign_id=self.ACTIVE_CAMPAIGN_ID, user_id=3,
                     product_id=self.REJECTED_ID, quantity=50),
        ])
        db.session.commit()
        set_annual_setting('limit_minimum_total', str(self.FINAL_TOTAL))
        set_annual_setting('limit_phase_one_order_limit', '550')
        set_annual_setting('limit_final_selection_limit', '2')
        self.archived_order = [(o.id, o.user_id, o.product_id, o.quantity)
                               for o in Order.query.filter_by(campaign_id=self.ARCHIVED_CAMPAIGN_ID)]
        # Simulated session identities require only TEST-scoped protection changes.
        self.app.login_manager.session_protection = None
        self.client = self.app.test_client()

    def tearDown(self):
        try:
            db.session.rollback()
            db.session.remove()
            db.drop_all()
        finally:
            self.context.pop()
            self.temporary.cleanup()

    def login_as(self, user_id):
        with self.client.session_transaction() as sess:
            sess['_user_id'] = str(user_id)
            sess['_fresh'] = True
        # Shared app context: Flask-Login caches the loaded identity on flask.g.
        # Clear the test cache after switching among fictional actors.
        g.pop('_login_user', None)

    def post_as(self, user_id, route, data=None):
        self.login_as(user_id)
        result = self.client.post(route, data=data or {}, follow_redirects=False)
        self.assertEqual(result.status_code, 302,
                         f'{route}: HTTP {result.status_code}: {result.get_data(as_text=True)[:400]}')
        return result

    def current_orders(self):
        return {(user_id, product_id): int(qty) for user_id, product_id, qty in
                db.session.query(Order.user_id, Order.product_id,
                                 db.func.sum(Order.quantity))
                  .filter(Order.campaign_id == self.ACTIVE_CAMPAIGN_ID)
                  .group_by(Order.user_id, Order.product_id).all()}

    def assert_previous_year_unchanged(self):
        rows = [(o.id, o.user_id, o.product_id, o.quantity)
                for o in Order.query.filter_by(campaign_id=self.ARCHIVED_CAMPAIGN_ID)]
        self.assertEqual(rows, self.archived_order)
        self.assertEqual(UserVote.query.filter_by(campaign_id=self.ARCHIVED_CAMPAIGN_ID,
                                                  product_id=90).one().quantity, 25)

    def advance_to_order_through_http(self):
        self.assertEqual(get_campaign_phase(), 'first')
        for route, next_phase in [
            ('/admin/phase/activate-second', 'second'),
            ('/admin/phase/advance-final', 'final'),
            ('/admin/phase/advance-order', 'order'),
        ]:
            self.post_as(self.ADMIN_ID, route)
            self.assertEqual(get_campaign_phase(), next_phase, route)
        selected = {p.id for p in Product.query.filter_by(campaign_id=self.ACTIVE_CAMPAIGN_ID,
                                                           final_selected=True)}
        self.assertEqual(selected, {self.RED_ID, self.BLUE_ID})
        self.assertEqual(self.current_orders(), {
            (1, self.RED_ID): 200, (1, self.BLUE_ID): 20,
            (2, self.RED_ID): 25, (2, self.BLUE_ID): 10,
            (3, self.RED_ID): 25,
        })
        self.assertEqual(Order.query.filter_by(campaign_id=self.ACTIVE_CAMPAIGN_ID,
                                                product_id=self.REJECTED_ID).count(), 0)
        self.assertEqual(UserVote.query.filter_by(campaign_id=self.ACTIVE_CAMPAIGN_ID,
                                                   product_id=self.REJECTED_ID).one().quantity, 50)
        assert_selected_commitments_materialized()
        self.assertEqual(materialize_selected_commitments(), (0, 0))
        self.assertEqual(Decimal(str(build_final_order_context()['base_total'])), self.BASE_TOTAL)
        self.assert_previous_year_unchanged()

    def assert_final_order_consistent(self):
        assert_selected_commitments_materialized()
        context = build_final_order_context()
        self.assertEqual(Decimal(str(context['base_total'])), self.FINAL_TOTAL)
        self.assertEqual(context['product_count'], 2)
        self.assertEqual(context['participant_count'], 3)
        self.assertEqual({r['product'].id: r['total_quantity']
                          for r in context['products']}, {self.RED_ID: 300, self.BLUE_ID: 30})
        self.assertEqual(self.current_orders(), {
            (1, self.RED_ID): 250, (1, self.BLUE_ID): 20,
            (2, self.RED_ID): 25, (2, self.BLUE_ID): 10,
            (3, self.RED_ID): 25,
        })
        self.assert_previous_year_unchanged()

    def finalize_export_through_http(self):
        self.post_as(self.ADMIN_ID, '/admin/order/generate')
        generated_at = get_annual_setting('final_order_generated_at')
        # A redirect also occurs on error: surface the actual flashed reason.
        with self.client.session_transaction() as session:
            messages = list(session.get('_flashes', ()))
        self.assertTrue(generated_at,
                        f'La ruta HTTP no genero el pedido. Mensajes: {messages!r}')
        excel = get_annual_setting('final_order_excel')
        self.assertTrue(excel and excel.endswith('.xlsx'))
        path = self.export_dir / excel
        self.assertTrue(path.is_file(), str(path))
        book = load_workbook(path, read_only=True, data_only=False)
        try:
            self.assertEqual(book.sheetnames, ['Pedido'])
            rows = list(book['Pedido'].values)
            self.assertEqual(rows[0], ('Referencia', 'Nombre', 'Color',
                                       'Precio unitario', 'Cantidad total', 'Importe total'))
            contents = {row[0]: (row[4], Decimal(str(row[5]))) for row in rows[1:-1]}
            self.assertEqual(contents, {
                'LADRILLO-ROJO': (300, Decimal('300')),
                'LADRILLO-AZUL': (30, Decimal('60')),
            })
            self.assertEqual(Decimal(str(rows[-1][5])), self.FINAL_TOTAL)
        finally:
            book.close()
        for key in ('final_order_piece_pdf', 'final_order_user_pdf'):
            filename = get_annual_setting(key)
            self.assertTrue(filename and filename.endswith('.zip'), key)
            with ZipFile(self.export_dir / filename) as bundle:
                self.assertIsNone(bundle.testzip(), filename)
                pdfs = [n for n in bundle.namelist() if n.lower().endswith('.pdf')]
                self.assertTrue(pdfs, f'No PDF in {filename}')
                for name in pdfs:
                    self.assertTrue(bundle.read(name).startswith(b'%PDF'), name)
        return path

    def assert_tampering_rejected_then_archive(self, excel_path):
        from app.services.campaign_archive import CampaignArchiveError, archive_completed_campaign
        from app.services.campaign_registry import create_next_campaign_draft

        with self.assertRaises(CampaignArchiveError):
            archive_completed_campaign(year=2025, export_folder=str(self.export_dir),
                                       actor_id=self.ADMIN_ID)
        original = excel_path.read_bytes()
        book = load_workbook(excel_path)
        book['Pedido'].cell(2, 5).value += 25
        book.save(excel_path)
        book.close()
        try:
            with self.assertRaises(CampaignArchiveError):
                archive_completed_campaign(year=2026, export_folder=str(self.export_dir),
                                           actor_id=self.ADMIN_ID)
            self.assertEqual(db.session.get(Campaign, self.ACTIVE_CAMPAIGN_ID).status,
                             'legacy_active', 'Tampering unexpectedly archived the year')
        finally:
            excel_path.write_bytes(original)

        saved_orders = self.current_orders()
        self.post_as(self.ADMIN_ID, '/admin/campaign-archive', {'confirm_year': '2026'})
        db.session.expire_all()
        active = db.session.get(Campaign, self.ACTIVE_CAMPAIGN_ID)
        self.assertEqual(active.status, 'archived')
        self.assertIsNotNone(active.archived_at)
        self.assertIsNone(current_campaign())
        self.assert_previous_year_unchanged()
        self.assertEqual(self.current_orders(), saved_orders)
        self.assertEqual(Config.get(annual_key('final_order_excel', self.ACTIVE_CAMPAIGN_ID)),
                         excel_path.name)

        draft = create_next_campaign_draft(year=2027,
                                           title='Campana simulada 2027',
                                           actor_id=self.ADMIN_ID)
        self.assertEqual(draft.status, 'draft')
        self.assertEqual(CampaignParticipation.query.filter_by(campaign_id=draft.id).count(), 0)
        self.assertEqual(Order.query.filter_by(campaign_id=draft.id).count(), 0)
        self.assertEqual(UserVote.query.filter_by(campaign_id=draft.id).count(), 0)
        self.assertEqual(Product.query.filter_by(campaign_id=draft.id).count(), 0)
        self.assert_previous_year_unchanged()
