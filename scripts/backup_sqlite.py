#!/usr/bin/env python3
"""Create a transactionally consistent online SQLite backup (never overwrites)."""
import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3
import sys
from urllib.parse import unquote


def backup(source, destination):
    src = Path(source)
    if not src.is_file():
        raise FileNotFoundError(f'SQLite database not found: {src}')
    dest = Path(destination)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        raise FileExistsError(f'Refusing to overwrite backup: {dest}')
    with sqlite3.connect(f'file:{src}?mode=ro', uri=True) as connection:
        with sqlite3.connect(str(dest)) as target:
            connection.backup(target)
            result = target.execute('PRAGMA integrity_check').fetchone()[0]
            if result != 'ok':
                raise RuntimeError(f'Backup integrity failed: {result}')
    os.chmod(dest, 0o600)
    return dest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', default=None)
    parser.add_argument('--destination', default=None)
    opts = parser.parse_args()
    url = os.environ.get('DATABASE_URL', 'sqlite:////data/db/app.sqlite')
    if not url.startswith('sqlite:////') and opts.source is None:
        parser.error('Only absolute SQLite DATABASE_URL supported')
    src = opts.source or unquote(url[len('sqlite:///'):])
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    dest = opts.destination or f'/data/backups/app-{timestamp}.sqlite'
    try:
        print(backup(src, dest))
    except Exception as exc:
        print(f'Backup failed: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
