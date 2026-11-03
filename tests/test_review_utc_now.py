"""Regresión de la revisión 2026-11-01 (ronda 3): utc_now() y regeneración síncrona.

Contrato: lo persistido es UTC sin tzinfo; utc_now() conserva valor y tipo de
datetime.utcnow() sin usar la API obsoleta desde Python 3.12.
"""
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app import db
from app.models import ActionLog
from app.services.campaign_settings import get_annual_setting, set_annual_setting
from app.time_utils import utc_now
from tests._v92_campaign_fixture import _V92CampaignFixture

ROOT = Path(__file__).resolve().parents[1]


def test_utc_now_is_naive_utc_and_iso_has_no_offset():
    value = utc_now()
    assert value.tzinfo is None
    assert abs(value - datetime.now(timezone.utc).replace(tzinfo=None)) < timedelta(seconds=2)
    assert not re.search(r'[+-]\d\d:\d\d$', value.isoformat())  # same format as old Config strings


def test_deprecated_api_does_not_come_back():
    """No real call or reference to utcnow/utcfromtimestamp in code (docstrings excluded)."""
    import ast
    offenders = []
    for folder in ('app', 'scripts', 'tests'):
        for path in (ROOT / folder).rglob('*.py'):
            tree = ast.parse(path.read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and node.attr in ('utcnow', 'utcfromtimestamp'):
                    offenders.append(f'{path.relative_to(ROOT)}:{node.lineno}')
    assert offenders == [], offenders


class UtcNowDatabaseContract(_V92CampaignFixture):
    def test_default_round_trips_and_compares_without_type_error(self):
        entry = ActionLog(user_id=self.ADMIN_ID, action='login')
        db.session.add(entry)
        db.session.commit()
        db.session.expire_all()
        stored = db.session.get(ActionLog, entry.id).created_at
        self.assertIsNone(stored.tzinfo)
        self.assertLess(abs(utc_now() - stored), timedelta(seconds=5))  # naive vs naive: no TypeError

    def test_regenerate_route_runs_synchronously(self):
        set_annual_setting('limit_minimum_total', '310')
        self.advance_to_order_through_http()
        self.post_as(self.ADMIN_ID, '/admin/order/generate')
        before = get_annual_setting('final_order_generated_at')
        self.assertTrue(before)
        time.sleep(1.1)  # export file names carry a per-second timestamp
        self.post_as(self.ADMIN_ID, '/admin/order/regenerate')
        with self.client.session_transaction() as session:
            messages = [m for _, m in session.get('_flashes', [])]
        self.assertIn('Archivos del pedido regenerados.', messages)
        self.assertNotEqual(get_annual_setting('final_order_generated_at'), before)
