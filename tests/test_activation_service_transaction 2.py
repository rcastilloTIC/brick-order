"""Execute the real annual activation service against SQLite without Flask."""
import ast
import os
import sqlite3
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]


class Row:
    def __init__(self, id, year, status):
        self.id, self.year, self.status = id, year, status


class Session:
    def __init__(self, connection):
        self.connection = connection
        self.pending = []
    def add(self, obj):
        self.pending.append(obj)
    def execute(self, statement, params):
        self.flush()
        cursor = self.connection.execute(str(statement), params)
        return cursor
    def flush(self):
        for obj in self.pending:
            self.connection.execute('INSERT INTO config (key, value) VALUES (?, ?)', (obj.key, obj.value))
        self.pending.clear()
    def commit(self):
        self.flush()
        self.connection.commit()
    def rollback(self):
        self.pending.clear()
        self.connection.rollback()


class Query:
    def __init__(self, connection, table):
        self.connection, self.table = connection, table
    def all(self):
        return [Row(*row) for row in self.connection.execute('SELECT id, year, status FROM campaign')]
    def filter_by(self, **kwargs):
        self.filter = kwargs
        return self
    def first(self):
        key = self.filter['key']
        return self.connection.execute('SELECT key FROM config WHERE key=?', (key,)).fetchone()


class Config:
    query = None
    def __init__(self, key, value):
        self.key, self.value = key, value


def load_actual_service(db):
    source = ROOT / 'app/services/campaign_activation.py'
    tree = ast.parse(source.read_text(encoding='utf-8'))
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                    and n.name == 'activate_prepared_draft')
    namespace = {'os': os, 'text': text, 'db': db, 'Campaign': types.SimpleNamespace(query=Query(db.session.connection, 'campaign')),
                 'Config': Config, 'phase_config_key': lambda id: f'phase_campaign_{id}',
                 'CampaignActivationError': type('CampaignActivationError', (ValueError,), {})}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), 'exec'), namespace)
    return namespace['activate_prepared_draft'], namespace['CampaignActivationError']


class ActivationServiceTransactionTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(':memory:')
        self.conn.execute('CREATE TABLE campaign (id INTEGER PRIMARY KEY, year INTEGER, status TEXT)')
        self.conn.execute('CREATE TABLE config (key TEXT UNIQUE, value TEXT)')
        self.conn.execute('CREATE TABLE audit (action TEXT)')
        self.conn.executemany('INSERT INTO campaign VALUES (?, ?, ?)', [(1, 2026, 'archived'), (2, 2027, 'draft')])
        self.conn.commit()
        self.session = Session(self.conn)
        self.db = types.SimpleNamespace(session=self.session)
        Config.query = Query(self.conn, 'config')
        self.activate, self.Error = load_actual_service(self.db)
        self.log_error = False
        def log_action(*args):
            if self.log_error:
                raise RuntimeError('Audit failed')
            self.conn.execute('INSERT INTO audit VALUES (?)', (args[1],))
        self.modules = {
            'app': types.ModuleType('app'),
            'app.services': types.ModuleType('app.services'),
            'app.services.annual_readiness': types.ModuleType('app.services.annual_readiness'),
            'app.services.activity_log': types.ModuleType('app.services.activity_log'),
            'app.services.campaign_calendar': types.ModuleType('app.services.campaign_calendar'),
        }
        self.modules['app.services.annual_readiness'].inspect_annual_readiness = lambda: {
            'database_consistent': True, 'draft_activation': {2027: {'data_prepared': True}}}
        self.modules['app.services.activity_log'].log_user_action = log_action
        calendar = self.modules['app.services.campaign_calendar']
        calendar.CampaignCalendarError = type('CampaignCalendarError', (ValueError,), {})
        calendar.read_campaign_window = lambda campaign: ('2027-10-01', '2028-03-31')
        calendar.other_campaign_windows = lambda campaign_id: []
        calendar.assert_no_window_overlap = lambda start, end, windows: None
        self.patch_modules = patch.dict(sys.modules, self.modules)
        self.patch_modules.start()
        self.patch_env = patch.dict(os.environ, {'ENABLE_ANNUAL_ACTIVATION': '1'})
        self.patch_env.start()

    def tearDown(self):
        self.patch_env.stop()
        self.patch_modules.stop()
        self.conn.close()

    def status(self):
        return self.conn.execute('SELECT status FROM campaign WHERE id=2').fetchone()[0]

    def test_activation_persists_phase_and_audit(self):
        self.activate(year=2027, actor_id=1, confirmation='ACTIVAR 2027')
        self.assertEqual(self.status(), 'legacy_active')
        self.assertEqual(self.conn.execute('SELECT value FROM config').fetchone()[0], 'first')
        self.assertEqual(self.conn.execute('SELECT count(*) FROM audit').fetchone()[0], 1)

    def test_missing_campaign_window_blocks_without_mutation(self):
        calendar = self.modules['app.services.campaign_calendar']
        calendar.read_campaign_window = lambda campaign: None
        with self.assertRaises(self.Error):
            self.activate(year=2027, actor_id=1, confirmation='ACTIVAR 2027')
        self.assertEqual(self.status(), 'draft')
        self.assertEqual(self.conn.execute('SELECT count(*) FROM config').fetchone()[0], 0)

    def test_overlapping_campaign_window_blocks_without_mutation(self):
        calendar = self.modules['app.services.campaign_calendar']
        def overlap(start, end, windows):
            raise calendar.CampaignCalendarError('Solapamiento de campañas')
        calendar.assert_no_window_overlap = overlap
        with self.assertRaises(self.Error):
            self.activate(year=2027, actor_id=1, confirmation='ACTIVAR 2027')
        self.assertEqual(self.status(), 'draft')
        self.assertEqual(self.conn.execute('SELECT count(*) FROM config').fetchone()[0], 0)

    def test_audit_failure_rolls_back_everything(self):
        self.log_error = True
        with self.assertRaises(self.Error):
            self.activate(year=2027, actor_id=1, confirmation='ACTIVAR 2027')
        self.assertEqual(self.status(), 'draft')
        self.assertEqual(self.conn.execute('SELECT count(*) FROM config').fetchone()[0], 0)
        self.assertEqual(self.conn.execute('SELECT count(*) FROM audit').fetchone()[0], 0)

    def test_existing_phase_blocks_without_mutation(self):
        self.conn.execute("INSERT INTO config VALUES ('phase_campaign_2', 'order')")
        self.conn.commit()
        with self.assertRaises(self.Error):
            self.activate(year=2027, actor_id=1, confirmation='ACTIVAR 2027')
        self.assertEqual(self.status(), 'draft')

    def test_invalid_confirmation_blocks_without_mutation(self):
        with self.assertRaises(self.Error):
            self.activate(year=2027, actor_id=1, confirmation='ACTIVAR 2026')
        self.assertEqual(self.status(), 'draft')

    def test_second_activation_cannot_repeat_audit(self):
        self.activate(year=2027, actor_id=1, confirmation='ACTIVAR 2027')
        with self.assertRaises(self.Error):
            self.activate(year=2027, actor_id=1, confirmation='ACTIVAR 2027')
        self.assertEqual(self.conn.execute('SELECT count(*) FROM audit').fetchone()[0], 1)

    def test_other_active_campaign_blocks_activation(self):
        self.conn.execute("UPDATE campaign SET status='legacy_active' WHERE id=1")
        self.conn.commit()
        with self.assertRaises(self.Error):
            self.activate(year=2027, actor_id=1, confirmation='ACTIVAR 2027')
        self.assertEqual(self.status(), 'draft')
        self.assertEqual(self.conn.execute('SELECT count(*) FROM config').fetchone()[0], 0)

    def test_release_flag_blocks_without_mutation(self):
        os.environ.pop('ENABLE_ANNUAL_ACTIVATION', None)
        with self.assertRaises(self.Error):
            self.activate(year=2027, actor_id=1, confirmation='ACTIVAR 2027')
        self.assertEqual(self.status(), 'draft')


if __name__ == '__main__':
    unittest.main()
