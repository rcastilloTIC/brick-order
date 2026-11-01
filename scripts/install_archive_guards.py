"""Optional immutable archived campaign SQLite triggers. Stop app and back up."""
import argparse
import sqlite3
from pathlib import Path
from urllib.parse import quote

TABLES = ('product', 'order', 'user_vote', 'user_favorite', 'campaign_participation')

class ArchiveGuardError(RuntimeError):
    pass

def install(database, *, apply=False):
    path = Path(database).resolve()
    if not path.is_file():
        raise ArchiveGuardError('Database does not exist')
    con = sqlite3.connect('file:' + quote(str(path), safe='/') + ('?mode=rw' if apply else '?mode=ro'), uri=True)
    try:
        existing = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if set(TABLES + ('campaign',)) - existing:
            raise ArchiveGuardError('Annual tables missing')
        for table in TABLES:
            if 'campaign_id' not in {row[1] for row in con.execute(f'PRAGMA table_info("{table}")')}:
                raise ArchiveGuardError(f'{table} lacks campaign_id')
        if not apply:
            return {'applied': False, 'tables': TABLES}
        con.execute('BEGIN IMMEDIATE')
        names = []
        for table in TABLES:
            for operation in ('INSERT', 'UPDATE', 'DELETE'):
                name = f'archive_{table}_{operation.lower()}_lock'
                names.append(name)
                refs = ('NEW',) if operation == 'INSERT' else (('OLD',) if operation == 'DELETE' else ('OLD','NEW'))
                checks = ' OR '.join(f"EXISTS (SELECT 1 FROM campaign WHERE id={ref}.campaign_id AND status='archived')" for ref in refs)
                con.execute(f'''CREATE TRIGGER IF NOT EXISTS "{name}" BEFORE {operation} ON "{table}" BEGIN
                    SELECT RAISE(ABORT, 'archived campaign is read-only') WHERE {checks}; END''')
        for operation in ('UPDATE', 'DELETE'):
            name = f'archive_campaign_{operation.lower()}_lock'
            names.append(name)
            con.execute(f'''CREATE TRIGGER IF NOT EXISTS "{name}" BEFORE {operation} ON campaign BEGIN
                SELECT RAISE(ABORT, 'archived campaign cannot be modified') WHERE OLD.status='archived'; END''')
        con.commit()
        return {'applied': True, 'triggers': len(names)}
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('database')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    try:
        print(install(args.database, apply=args.apply))
    except (ArchiveGuardError, sqlite3.Error) as exc:
        parser.exit(1, f'ERROR: {exc}\n')
