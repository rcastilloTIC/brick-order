"""V87: CLI behavior during off-season; no production database used."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from app import create_app, db
from app.models import Campaign

class MaintenanceCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='valbrick-v87-')
        directory = Path(self.temp.name)
        class TestConfig:
            TESTING = True
            SECRET_KEY = 'v87-tests-not-production'
            SQLALCHEMY_DATABASE_URI = 'sqlite:///' + str(directory/'test.sqlite')
            SQLALCHEMY_TRACK_MODIFICATIONS = False
            SITE_ACCESS_PASSWORD = None
            DECLARATION_UPLOAD_FOLDER = str(directory/'declarations')
            ORDER_EXPORT_FOLDER = str(directory/'exports')
            BACKUP_FOLDER = str(directory/'backups')
            TRUSTED_PROXY_COUNT = 0
            RATELIMIT_STORAGE_URI = 'memory://'
            DEFAULT_LANGUAGE = 'es'
            SUPPORTED_LANGUAGES = ('es','en')
        self.app = create_app(TestConfig)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()
        self.temp.cleanup()

    def test_empty_campaign_skips_capture_without_error(self):
        result = self.app.test_cli_runner().invoke(args=['capture-insights'])
        self.assertEqual(result.exit_code, 0, str(result.exception))
        self.assertIn('SKIPPED: no active campaign', result.output)

    def test_archived_campaign_skips_capture(self):
        db.session.add(Campaign(year=2025, title='Archived 2025', status='archived'))
        db.session.commit()
        result = self.app.test_cli_runner().invoke(args=['capture-insights'])
        self.assertEqual(result.exit_code, 0, str(result.exception))
        self.assertIn('SKIPPED:', result.output)
        self.assertEqual(Campaign.query.count(), 1)

    def test_bad_registry_remains_a_failure(self):
        with patch('app.services.active_campaign.current_campaign', side_effect=RuntimeError('Inconsistent campaign registry')):
            result = self.app.test_cli_runner().invoke(args=['capture-insights'])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIsInstance(result.exception, RuntimeError)
