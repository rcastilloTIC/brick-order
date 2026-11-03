"""V88 HTTP checks use a local Flask test client and a disposable DB."""
import tempfile
import unittest
from pathlib import Path
from app import create_app, db
from app.models import User, Campaign, CampaignParticipation

class V88HttpSecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='valbrick-v88-http-')
        folder=Path(self.temp.name)
        class TestConfig:
            TESTING=True
            SECRET_KEY='v88-test-key-only'
            SQLALCHEMY_DATABASE_URI='sqlite:///'+str(folder/'test.sqlite')
            SQLALCHEMY_TRACK_MODIFICATIONS=False
            SITE_ACCESS_PASSWORD=None
            DECLARATION_UPLOAD_FOLDER=str(folder/'declarations')
            ORDER_EXPORT_FOLDER=str(folder/'exports')
            BACKUP_FOLDER=str(folder/'backups')
            TRUSTED_PROXY_COUNT=0
            RATELIMIT_STORAGE_URI='memory://'
            WTF_CSRF_ENABLED=False
            DEFAULT_LANGUAGE='es'
            SUPPORTED_LANGUAGES=('es','en')
        self.app=create_app(TestConfig)
        self.ctx=self.app.app_context();self.ctx.push()
        db.create_all()
        db.session.add(Campaign(id=1,year=2026,title='Fictional',status='legacy_active'))
        db.session.add(User(id=1,username='visitor',password_hash='unusable',is_admin=False,active=True,must_change_password=False))
        db.session.add(User(id=2,username='admin',password_hash='unusable',is_admin=True,active=True,must_change_password=False))
        db.session.flush()
        db.session.add(CampaignParticipation(campaign_id=1,user_id=1,status='approved',signed_document='fixture-test-only.pdf'))
        db.session.commit()
        # The test manually injects a user id. Disable Flask-Login session
        # fingerprint protection *only for this test app*: production remains unchanged.
        self.app.login_manager.session_protection = None
        self.client=self.app.test_client()

    def tearDown(self):
        db.session.remove();db.drop_all();self.ctx.pop();self.temp.cleanup()

    def login_as(self,user_id):
        with self.client.session_transaction() as session:
            session['_user_id']=str(user_id)
            session['_fresh']=True

    def test_anonymous_denied_sensitive_routes(self):
        for path in ('/admin/shortage','/shortage/increase'):
            result=self.client.get(path,follow_redirects=False)
            self.assertIn(result.status_code,(302,401,403),path)

    def test_participant_cannot_read_admin_shortage(self):
        self.login_as(1)
        self.assertEqual(self.client.get('/admin/shortage').status_code,403)
        self.assertEqual(self.client.post('/admin/shortage',data={'action':'cancel','confirm':'CANCELAR'}).status_code,403)

    def test_admin_cannot_use_participant_increase(self):
        self.login_as(2)
        self.assertEqual(self.client.get('/shortage/increase').status_code,403)
        self.assertEqual(self.client.post('/shortage/acknowledge',data={'read':'yes'}).status_code,403)

    def test_onboarding_redirects_still_apply_before_role_checks(self):
        user=db.session.get(User,1)
        user.must_change_password=True
        db.session.commit()
        self.login_as(1)
        response=self.client.get('/admin/shortage',follow_redirects=False)
        self.assertEqual(response.status_code,302)
        self.assertIn('password',response.headers['Location'].lower())

    def test_participant_not_approved_is_denied(self):
        participation=CampaignParticipation.query.filter_by(campaign_id=1,user_id=1).one()
        participation.status='pending_commitment'
        db.session.commit()
        self.login_as(1)
        response=self.client.get('/admin/shortage',follow_redirects=False)
        self.assertIn(response.status_code,(302,403))
        self.assertNotEqual(response.status_code,200)
