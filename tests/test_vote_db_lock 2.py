"""Real SQLite tests, no mocked HTTP or source string inspection."""
import importlib.util
import sqlite3
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('vote_db_lock', ROOT / 'scripts' / 'install_vote_lock.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


@pytest.fixture
def database(tmp_path):
    path = tmp_path / 'sample.sqlite'
    with sqlite3.connect(path) as db:
        db.executescript('''CREATE TABLE user_vote (
            id INTEGER PRIMARY KEY, campaign_id INTEGER, user_id INTEGER,
            product_id INTEGER, quantity INTEGER, initial_quantity INTEGER, phase TEXT);
            INSERT INTO user_vote VALUES (1,1,5,10,50,50,'first');''')
    return path


def test_dry_run_is_read_only(database):
    assert mod.install(database)['applied'] is False
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='trigger'").fetchone()[0] == 0


def test_installer_idempotent_and_increasing_vote(database):
    assert mod.install(database, apply=True)['triggers'] == 3
    mod.install(database, apply=True)
    with sqlite3.connect(database) as db:
        db.execute('UPDATE user_vote SET quantity=75 WHERE id=1')
        db.execute('UPDATE user_vote SET quantity=75 WHERE id=1')
        assert db.execute('SELECT quantity FROM user_vote WHERE id=1').fetchone()[0] == 75


@pytest.mark.parametrize('sql', [
    'UPDATE user_vote SET quantity=49 WHERE id=1',
    'UPDATE user_vote SET quantity=0 WHERE id=1',
    'UPDATE user_vote SET quantity=NULL WHERE id=1',
    'UPDATE user_vote SET quantity=50.5 WHERE id=1',
    'UPDATE user_vote SET user_id=6 WHERE id=1',
    'UPDATE user_vote SET campaign_id=2 WHERE id=1',
    'DELETE FROM user_vote WHERE id=1',
    'INSERT INTO user_vote(id,campaign_id,user_id,product_id,quantity) VALUES(2,1,5,11,0)',
    'INSERT INTO user_vote(id,campaign_id,user_id,product_id,quantity) VALUES(2,1,5,11,2.5)',
])
def test_invalid_mutations_rejected(database, sql):
    mod.install(database, apply=True)
    with sqlite3.connect(database) as db:
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(sql)


def test_historical_vote_remains_after_cutoff(database):
    mod.install(database, apply=True)
    with sqlite3.connect(database) as db:
        assert db.execute('SELECT quantity FROM user_vote WHERE product_id=10').fetchone()[0] == 50


def test_dirty_data_prevents_install(database):
    with sqlite3.connect(database) as db:
        db.execute('UPDATE user_vote SET quantity=0')
    with pytest.raises(mod.VoteLockError):
        mod.install(database, apply=True)
