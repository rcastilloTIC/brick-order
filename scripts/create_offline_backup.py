#!/usr/bin/env python3
"""Consistent full ZIP backup while VALBRICK and scheduler are STOPPED."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from zipfile import ZipFile, ZIP_DEFLATED

PHASES = {'PUBLICA': {'first', 'second', 'final', 'order'},
          'EXTENDED': {'first', 'second', 'extension', 'final', 'order', 'final_extension'}}


def _phase_from_database(path: Path, edition: str) -> str:
    with sqlite3.connect(f'{path.as_uri()}?mode=ro', uri=True) as conn:
        campaigns = conn.execute("SELECT id FROM campaign WHERE status='legacy_active'").fetchall()
        if len(campaigns) > 1:
            raise ValueError('Ambiguous operational campaign')
        if not campaigns:
            return 'first'
        phase = conn.execute('SELECT value FROM config WHERE key=?',
                             (f'phase_campaign_{campaigns[0][0]}',)).fetchone()
        if not phase:
            phase = conn.execute("SELECT value FROM config WHERE key='phase'").fetchone()
        value = phase[0] if phase else 'first'
        if value not in PHASES[edition]:
            raise ValueError('Invalid stored campaign phase')
        return value


def backup(data_dir: Path, target: Path, edition: str) -> Path:
    data_dir = data_dir.resolve(strict=True)
    if edition not in PHASES:
        raise ValueError('Wrong edition')
    db_file = data_dir / 'db' / 'app.sqlite'
    if not db_file.is_file():
        raise FileNotFoundError(f'No SQLite file: {db_file}')
    phase = _phase_from_database(db_file, edition)
    target = target.absolute()
    target.parent.mkdir(parents=True, exist_ok=True)
    manifest = dict(version=1, edition=edition,
                    created_at=datetime.now(timezone.utc).isoformat(),
                    phase_at_backup=phase, target_phase=phase,
                    db_filename='database.sqlite3',
                    paths={'declarations': 'declarations', 'exports': 'exports'})
    # Do not trust symlinked document directories to remain within the data volume.
    for name in ('declarations', 'exports'):
        directory = data_dir / name
        if directory.is_symlink():
            raise ValueError('Symlinked document directory')
        if directory.exists():
            for path in directory.rglob('*'):
                if path.is_symlink():
                    raise ValueError(f'Symlink in backup source: {path}')
    with tempfile.TemporaryDirectory(prefix='valbrick-offline-', dir=target.parent) as temporary:
        snapshot = Path(temporary) / 'snapshot.sqlite'
        with sqlite3.connect(f'{db_file.as_uri()}?mode=ro', uri=True) as original:
            with sqlite3.connect(snapshot) as output:
                original.backup(output)
        temp_zip = Path(temporary) / 'backup.zip'
        with ZipFile(temp_zip, 'w', compression=ZIP_DEFLATED) as archive:
            archive.writestr('manifest.json', json.dumps(manifest, indent=2))
            archive.write(snapshot, 'database.sqlite3')
            for name in ('declarations', 'exports'):
                directory = data_dir / name
                if not directory.is_dir():
                    continue
                for path in sorted(directory.rglob('*')):
                    if path.is_file():
                        archive.write(path, f'{name}/{path.relative_to(directory).as_posix()}')
        with ZipFile(temp_zip) as archive:
            if archive.testzip() is not None:
                raise ValueError('ZIP verification failed')
        # The temp ZIP might be in a subdir of target.parent; move atomically to target.
        os.replace(temp_zip, target)
    if os.geteuid() == 0:
        owner = data_dir.stat()
        os.chown(target, owner.st_uid, owner.st_gid)
    target.chmod(0o600)
    return target


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data-dir', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--edition', choices=sorted(PHASES), required=True)
    p.add_argument('--confirm', required=True)
    a = p.parse_args()
    if a.confirm != 'BACKUP_OFFLINE':
        p.error('Stop app and scheduler, then --confirm BACKUP_OFFLINE')
    out = backup(a.data_dir, a.output, a.edition)
    print('Verified ZIP created:', out)

if __name__ == '__main__':
    main()
