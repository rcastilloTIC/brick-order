"""Validate critical deployment safety defaults without a running Docker daemon."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ComposeSafetyTest(unittest.TestCase):
    def test_compose_forces_production_configuration(self):
        compose = (ROOT / 'docker-compose.yml').read_text(encoding='utf-8')
        self.assertIn('FLASK_ENV: production', compose)
        self.assertIn('SESSION_COOKIE_SECURE: "${SESSION_COOKIE_SECURE:-true}"', compose)

    def test_healthcheck_and_persisted_database(self):
        compose = (ROOT / 'docker-compose.yml').read_text(encoding='utf-8')
        self.assertIn('healthcheck:', compose)
        self.assertIn('socket.create_connection', compose)
        self.assertIn('DATABASE_URL: sqlite:////data/db/app.sqlite', compose)
        self.assertIn('./data:/data', compose)

    def test_build_context_excludes_secrets(self):
        ignored = (ROOT / '.dockerignore').read_text(encoding='utf-8').splitlines()
        for name in ('.env', 'data', '.git', '.venv'):
            self.assertIn(name, ignored)


if __name__ == '__main__':
    unittest.main()
