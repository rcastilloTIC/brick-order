"""Explicit, non-destructive SQLite preparation for annual data isolation.

This is an EXPAND migration only. The live application still operates with a
single campaign: do not activate another campaign after running this script.

Usage: python scripts/prepare_campaign_columns.py /path/to/database.db
       python scripts/prepare_campaign_columns.py /path/to/database.db --apply

On --apply an SQLite online backup is made before any ALTER TABLE. This script
refuses databases with multiple campaigns, ambiguous/unregistered campaigns,
incomplete schemas, or existing rows assigned to a different campaign.
"""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import sys

TABLES = ('product', 'order', 'user_vote', 'user_favorite')


class MigrationError(RuntimeError):
    pass


def prepare(db_path: Path, apply: bool = False) -> dict:
    db_path = Path(db_path).resolve()
    if not db_path.is_file():
        raise MigrationError(f'Database not found: {db_path}')
    # mode=rw ensures we never create an unexpected empty database.
    from urllib.parse import quote
    uri = 'file:' + quote(str(db_path), safe='/') + '?mode=rw'
    conn = sqlite3.connect(uri, uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute('PRAGMA busy_timeout=10000')
        tables = {r['name'] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not set(TABLES + ('campaign',)).issubset(tables):
            raise MigrationError('Required tables missing; register existing campaign first')
        campaigns = conn.execute('SELECT id, year FROM campaign ORDER BY id').fetchall()
        if len(campaigns) != 1:
            raise MigrationError('Exactly one registered campaign is required')
        campaign_id = campaigns[0]['id']
        modifications = []
        counts = {}
        for table in TABLES:
            columns = {r['name'] for r in conn.execute(f'PRAGMA table_info("{table}")')}
            if 'campaign_id' not in columns:
                modifications.append(table)
            else:
                conflict = conn.execute(f'SELECT COUNT(*) FROM "{table}" WHERE campaign_id IS NOT NULL AND campaign_id != ?', (campaign_id,)).fetchone()[0]
                if conflict:
                    raise MigrationError(f'{table} contains records from another campaign')
            counts[table] = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        result = {'campaign_id': campaign_id, 'year': campaigns[0]['year'],
                  'new_columns': modifications, 'rows': counts, 'applied': False}
        if not apply:
            return result
        # VACUUM INTO is not portable to old SQLite; use online backup API.
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        backup = db_path.with_name(db_path.name + f'.before-annual-{stamp}.bak')
        if backup.exists():
            raise MigrationError('Backup file already exists')
        with sqlite3.connect(backup) as backup_conn:
            conn.backup(backup_conn)
        result['backup'] = str(backup)
        # Acquire a reserved writer lock and re-check campaign registry.
        conn.execute('BEGIN IMMEDIATE')
        try:
            current = conn.execute('SELECT id FROM campaign').fetchall()
            if len(current) != 1 or current[0][0] != campaign_id:
                raise MigrationError('Campaign changed while preparing migration')
            for table in TABLES:
                if table in modifications:
                    conn.execute(f'ALTER TABLE "{table}" ADD COLUMN campaign_id INTEGER REFERENCES campaign(id)')
                conn.execute(f'UPDATE "{table}" SET campaign_id = ? WHERE campaign_id IS NULL', (campaign_id,))
                conn.execute(f'CREATE INDEX IF NOT EXISTS "ix_{table}_campaign_id" ON "{table}" (campaign_id)')
                unset = conn.execute(f'SELECT COUNT(*) FROM "{table}" WHERE campaign_id IS NULL').fetchone()[0]
                if unset:
                    raise MigrationError(f'{table} contains unassigned rows')
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        result['applied'] = True
        return result
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('database', type=Path)
    parser.add_argument('--apply', action='store_true', help='Backup and add campaign_id columns')
    args = parser.parse_args()
    try:
        result = prepare(args.database, args.apply)
    except (MigrationError, sqlite3.DatabaseError, OSError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1
    print(result)
    return 0


if __name__ == '__main__':
    sys.exit(main())
