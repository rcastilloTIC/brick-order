"""Executable SQLite diagnostic coverage without Flask application setup."""
import importlib.util
import sqlite3
import sys
import types
from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session


def load_service(monkeypatch):
    engine = create_engine('sqlite:///:memory:')
    @event.listens_for(engine, 'connect')
    def fk_on(connection, record):
        connection.execute('PRAGMA foreign_keys=OFF')
    with engine.begin() as c:
        c.exec_driver_sql('CREATE TABLE campaign (id INTEGER PRIMARY KEY, year INT, status TEXT)')
        c.exec_driver_sql('CREATE TABLE product (id INTEGER PRIMARY KEY, campaign_id INT)')
        c.exec_driver_sql('CREATE TABLE campaign_participation (id INTEGER PRIMARY KEY, campaign_id INT, user_id INT, status TEXT, signed_document TEXT)')
        for name in ('user_vote', 'user_favorite', 'order'):
            c.exec_driver_sql(f'CREATE TABLE "{name}" (id INTEGER PRIMARY KEY, campaign_id INT, user_id INT, product_id INT)')
    session = Session(engine)
    stub=types.ModuleType('app'); stub.db=types.SimpleNamespace(session=session, engine=engine)
    monkeypatch.setitem(sys.modules,'app',stub)
    services_stub = types.ModuleType('app.services'); services_stub.__path__ = []
    monkeypatch.setitem(sys.modules, 'app.services', services_stub)
    preflight_location = Path(__file__).resolve().parents[1]/'app/services/draft_activation_preflight.py'
    preflight_spec = importlib.util.spec_from_file_location('app.services.draft_activation_preflight', preflight_location)
    preflight = importlib.util.module_from_spec(preflight_spec)
    preflight_spec.loader.exec_module(preflight)
    monkeypatch.setitem(sys.modules, 'app.services.draft_activation_preflight', preflight)
    location=Path(__file__).resolve().parents[1]/'app/services/annual_readiness.py'
    spec=importlib.util.spec_from_file_location('_annual_readiness',location)
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return session, module


def test_clean_archived_year_and_draft(monkeypatch):
    from sqlalchemy import text
    session, service = load_service(monkeypatch)
    session.execute(text("INSERT INTO campaign VALUES (1, 2026, 'archived'), (2, 2027, 'draft')"))
    session.execute(text('INSERT INTO product VALUES (1, 1)'))
    session.execute(text('INSERT INTO campaign_participation (id, campaign_id, user_id) VALUES (1, 1, 10)'))
    session.execute(text('INSERT INTO user_vote VALUES (1, 1, 10, 1)'))
    report = service.inspect_annual_readiness()
    assert report['database_consistent'] is True
    assert report['activation_enabled'] is False


def test_cross_year_product_and_missing_membership(monkeypatch):
    from sqlalchemy import text
    session, service = load_service(monkeypatch)
    session.execute(text("INSERT INTO campaign VALUES (1, 2026, 'archived'), (2, 2027, 'draft')"))
    session.execute(text('INSERT INTO product VALUES (1, 1)'))
    session.execute(text('INSERT INTO user_vote VALUES (1, 2, 10, 1)'))
    findings = service.inspect_annual_readiness()['findings']
    assert any('productos de otra campaña' in f for f in findings)
    assert any('sin inscripción anual' in f for f in findings)
    assert any('Borrador 2027' in f for f in findings)


def test_unassigned_and_dangling_records(monkeypatch):
    from sqlalchemy import text
    session, service = load_service(monkeypatch)
    session.execute(text("INSERT INTO campaign VALUES (1, 2026, 'archived'), (2, 2027, 'draft')"))
    session.execute(text('INSERT INTO product VALUES (1, NULL), (2, 99)'))
    findings=service.inspect_annual_readiness()['findings']
    assert any('sin campaña' in f for f in findings)
    assert any('campaña inexistente' in f for f in findings)


def test_draft_catalogue_and_roster_are_valid_preparation(monkeypatch):
    from sqlalchemy import text
    session, service = load_service(monkeypatch)
    session.execute(text("INSERT INTO campaign VALUES (1, 2026, 'archived'), (2, 2027, 'draft')"))
    session.execute(text('INSERT INTO product VALUES (10, 2)'))
    session.execute(text('INSERT INTO campaign_participation (id, campaign_id, user_id) VALUES (10, 2, 55)'))
    report = service.inspect_annual_readiness()
    assert report['database_consistent'] is True
    assert report['activation_enabled'] is False
    assert report['draft_preparation'][2027]['product'] == 1
    assert report['draft_preparation'][2027]['campaign_participation'] == 1


def test_draft_operational_records_remain_blockers(monkeypatch):
    from sqlalchemy import text
    session, service = load_service(monkeypatch)
    session.execute(text("INSERT INTO campaign VALUES (1, 2026, 'archived'), (2, 2027, 'draft')"))
    session.execute(text('INSERT INTO product VALUES (10, 2)'))
    session.execute(text('INSERT INTO campaign_participation (id, campaign_id, user_id) VALUES (10, 2, 55)'))
    session.execute(text('INSERT INTO "order" VALUES (10, 2, 55, 10)'))
    report = service.inspect_annual_readiness()
    assert report['database_consistent'] is False
    assert report['activation_enabled'] is False
    assert any('registros operativos en order' in item for item in report['findings'])
