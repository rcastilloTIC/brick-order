"""Install opt-in SQLite vote quantity guards (requires stopped app and backup)."""
import argparse
import sqlite3
from pathlib import Path
from urllib.parse import quote


class VoteLockError(RuntimeError):
    pass


def install(database, *, apply=False):
    path = Path(database).resolve()
    if not path.is_file():
        raise VoteLockError('Database file does not exist')
    uri = 'file:' + quote(str(path), safe='/') + ('?mode=rw' if apply else '?mode=ro')
    con = sqlite3.connect(uri, uri=True, timeout=15)
    try:
        columns = {row[1] for row in con.execute('PRAGMA table_info(user_vote)')}
        required = {'id', 'quantity', 'user_id', 'product_id', 'campaign_id'}
        if not required <= columns:
            raise VoteLockError('Missing user_vote columns: ' + ', '.join(sorted(required - columns)))
        invalid = con.execute("SELECT COUNT(*) FROM user_vote WHERE typeof(quantity) != 'integer' OR quantity <= 0").fetchone()[0]
        if invalid:
            raise VoteLockError(f'{invalid} existing votes have invalid quantities')
        if not apply:
            return {'applied': False, 'votes': con.execute('SELECT COUNT(*) FROM user_vote').fetchone()[0]}
        con.execute('BEGIN IMMEDIATE')
        statements = (
            """CREATE TRIGGER IF NOT EXISTS lock_vote_insert BEFORE INSERT ON user_vote BEGIN
               SELECT RAISE(ABORT, 'vote quantity must be positive integer')
               WHERE typeof(NEW.quantity) != 'integer' OR NEW.quantity <= 0;
            END""",
            """CREATE TRIGGER IF NOT EXISTS lock_vote_update BEFORE UPDATE ON user_vote BEGIN
               SELECT RAISE(ABORT, 'vote identity cannot change')
               WHERE NEW.id IS NOT OLD.id OR NEW.user_id IS NOT OLD.user_id
                  OR NEW.product_id IS NOT OLD.product_id OR NEW.campaign_id IS NOT OLD.campaign_id;
               SELECT RAISE(ABORT, 'vote commitment cannot decrease')
               WHERE typeof(NEW.quantity) != 'integer' OR NEW.quantity <= 0 OR NEW.quantity < OLD.quantity;
            END""",
            """CREATE TRIGGER IF NOT EXISTS lock_vote_delete BEFORE DELETE ON user_vote BEGIN
               SELECT RAISE(ABORT, 'vote commitment cannot be deleted');
            END""",
        )
        for statement in statements:
            con.execute(statement)
        con.commit()
        return {'applied': True, 'triggers': len(statements)}
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('database')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    try:
        print(install(args.database, apply=args.apply))
    except (VoteLockError, sqlite3.Error) as exc:
        parser.exit(1, f'ERROR: {exc}\n')


if __name__ == '__main__':
    main()
