import importlib.util
import sqlite3
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('guards', ROOT / 'scripts' / 'install_campaign_guards.py')
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)

@pytest.fixture
def dbfile(tmp_path):
    path = tmp_path / 'data.db'
    with sqlite3.connect(path) as c:
        c.executescript('''CREATE TABLE campaign(id INTEGER PRIMARY KEY);
          CREATE TABLE campaign_participation(user_id INT, campaign_id INT);
          CREATE TABLE product(id INTEGER PRIMARY KEY,campaign_id INT);
          CREATE TABLE "order"(id INTEGER PRIMARY KEY,campaign_id INT,user_id INT,product_id INT);
          CREATE TABLE user_vote(id INTEGER PRIMARY KEY,campaign_id INT,user_id INT,product_id INT);
          CREATE TABLE user_favorite(id INTEGER PRIMARY KEY,campaign_id INT,user_id INT,product_id INT);
          INSERT INTO campaign VALUES(1);INSERT INTO product VALUES(10,1);
          INSERT INTO campaign_participation VALUES(2,1);''')
    return path

def test_installer_dry_run(dbfile):
    assert g.install(dbfile)['applied'] is False
    with sqlite3.connect(dbfile) as c:
        assert c.execute("select count(*) from sqlite_master where type='trigger'").fetchone()[0] == 0

def test_install_and_idempotence(dbfile):
    assert g.install(dbfile, apply=True)['triggers'] == 8
    assert g.install(dbfile, apply=True)['triggers'] == 8

def test_reject_invalid_insert_and_update(dbfile):
    g.install(dbfile, apply=True)
    with sqlite3.connect(dbfile) as c:
        c.execute('INSERT INTO "order"(id,campaign_id,user_id,product_id) VALUES(1,1,2,10)')
        for query in (
            'INSERT INTO "order" VALUES(2,NULL,2,10)',
            'INSERT INTO user_vote VALUES(1,1,3,10)',
            'INSERT INTO user_favorite VALUES(1,1,2,999)',
            'UPDATE "order" SET user_id=3 WHERE id=1',
            'UPDATE product SET campaign_id=2 WHERE id=10',
        ):
            with pytest.raises(sqlite3.IntegrityError):
                c.execute(query)

def test_reject_cross_campaign(dbfile):
    g.install(dbfile, apply=True)
    with sqlite3.connect(dbfile) as c:
        c.execute('INSERT INTO campaign VALUES(2)')
        c.execute('INSERT INTO product VALUES(11,2)')
        with pytest.raises(sqlite3.IntegrityError):
            c.execute('INSERT INTO user_vote VALUES(1,1,2,11)')

def test_existing_wrong_ownership_refused(dbfile):
    with sqlite3.connect(dbfile) as c:
        c.execute('INSERT INTO "order" VALUES(1,1,8,10)')
    with pytest.raises(g.GuardError):
        g.install(dbfile, apply=True)
