#!/usr/bin/env python3
"""Offline, reversible restore for a V92+ VALBRICK backup ZIP.

Only run with the app and any external scheduler STOPPED. Requires Python 3.11
stdlib only. The CLI refuses unsafe ZIP members, malformed manifests and
wrong-edition databases. Never writes into live data until preflight succeeds.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import stat
import tempfile
from zipfile import BadZipFile, ZipFile

MAX_FILES = 10000
MAX_UNCOMPRESSED = 2 * 1024 * 1024 * 1024
REQUIRED_TABLES = {'campaign', 'campaign_participation', 'user', 'product', 'user_vote', 'order', 'config'}
PRIVATE_TABLES = {'extension_interest', 'final_extension_interest'}
PHASES = {'PUBLICA': {'first', 'second', 'final', 'order'},
          'EXTENDED': {'first', 'second', 'extension', 'final', 'order', 'final_extension'}}


class UnsafeRestore(ValueError):
    pass


def validate_archive(archive_path: Path, unpack_dir: Path, edition: str) -> dict:
    """Read and unpack only known archive entries to a disposable directory."""
    if edition not in PHASES:
        raise UnsafeRestore('Unknown edition')
    total = 0
    names = set()
    try:
        with ZipFile(archive_path) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_FILES:
                raise UnsafeRestore('Too many ZIP members')
            for item in infos:
                name = item.filename
                path = PurePosixPath(name)
                if (not name or '\\' in name or path.is_absolute()
                        or any(part in ('', '.', '..') for part in path.parts)
                        or ':' in path.parts[0]):
                    raise UnsafeRestore('Unsafe archive path')
                normalized = str(path).rstrip('/')
                if normalized in names:
                    raise UnsafeRestore('Duplicate archive name')
                names.add(normalized)
                if not (normalized in {'manifest.json', 'database.sqlite3'}
                        or normalized in {'declarations', 'exports'}
                        or normalized.startswith(('declarations/', 'exports/'))):
                    raise UnsafeRestore('Unexpected path in backup')
                mode = (item.external_attr >> 16) & 0xFFFF
                if stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR)):
                    raise UnsafeRestore('Unsafe archive member type')
                total += item.file_size
                if total > MAX_UNCOMPRESSED:
                    raise UnsafeRestore('Backup uncompressed size is too large')
            if not {'manifest.json', 'database.sqlite3'} <= names:
                raise UnsafeRestore('Missing manifest or SQLite database')
            if archive.testzip() is not None:
                raise UnsafeRestore('ZIP checksum error')
            for item in infos:
                path = unpack_dir / item.filename
                if item.is_dir():
                    path.mkdir(parents=True, exist_ok=True)
                else:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(item) as src, path.open('xb') as target:
                        shutil.copyfileobj(src, target)
    except (OSError, BadZipFile, RuntimeError) as exc:
        raise UnsafeRestore(f'Corrupt or unreadable backup: {exc}') from exc

    try:
        manifest = json.loads((unpack_dir / 'manifest.json').read_text(encoding='utf-8'))
    except (ValueError, UnicodeError, OSError) as exc:
        raise UnsafeRestore(f'Invalid backup manifest: {exc}') from exc
    if not isinstance(manifest, dict) or manifest.get('version') != 1:
        raise UnsafeRestore('Unsupported backup manifest version')
    if manifest.get('db_filename') != 'database.sqlite3':
        raise UnsafeRestore('Unexpected database path in manifest')
    paths = manifest.get('paths')
    if not isinstance(paths, dict) or paths != {'declarations': 'declarations', 'exports': 'exports'}:
        raise UnsafeRestore('Unsafe backup folder mapping')
    if (manifest.get('phase_at_backup') not in PHASES[edition]
            or manifest.get('target_phase') not in PHASES[edition]):
        raise UnsafeRestore('Invalid phase for edition')
    if manifest.get('edition') is not None and manifest['edition'] != edition:
        raise UnsafeRestore('Backup edition does not match the destination')

    db_file = unpack_dir / 'database.sqlite3'
    if not db_file.is_file() or not db_file.stat().st_size:
        raise UnsafeRestore('Empty SQLite database')
    try:
        with sqlite3.connect(f'{db_file.as_uri()}?mode=ro', uri=True) as db:
            if db.execute('PRAGMA integrity_check').fetchone() != ('ok',):
                raise UnsafeRestore('SQLite integrity check failed')
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    except sqlite3.DatabaseError as exc:
        raise UnsafeRestore(f'Invalid SQLite database: {exc}') from exc
    if not REQUIRED_TABLES <= tables:
        raise UnsafeRestore('Missing core VALBRICK database tables')
    if edition == 'PUBLICA' and PRIVATE_TABLES & tables:
        raise UnsafeRestore('Extended private tables cannot be restored into Publica')
    if edition == 'EXTENDED' and not PRIVATE_TABLES <= tables:
        raise UnsafeRestore('Extended database lacks its private tables')
    return manifest


def _reject_existing_symlinks(data_dir: Path):
    if data_dir.is_symlink():
        raise UnsafeRestore('The data folder cannot be a symlink')
    if data_dir.exists():
        for candidate in data_dir.rglob('*'):
            if candidate.is_symlink():
                raise UnsafeRestore('Refusing to copy a data folder containing symlinks')


def _activate(stage: Path, destination: Path, previous: Path, *, simulate_failure=False):
    """Switch an entire data tree; roll back on a failure during replacement."""
    moved_old = False
    installed = False
    try:
        if destination.exists():
            os.replace(destination, previous)
            moved_old = True
        if simulate_failure:
            raise OSError('Simulated swap failure')
        os.replace(stage, destination)
        installed = True
    except BaseException:
        if moved_old and not installed:
            os.replace(previous, destination)
        raise


def restore(archive_path: Path, data_dir: Path, edition: str, *, simulate_failure=False) -> Path | None:
    archive_path = archive_path.resolve(strict=True)
    data_dir = data_dir.absolute()
    if data_dir.name != 'data':
        raise UnsafeRestore('Destination must be the data/ directory of this project')
    if not data_dir.parent.exists():
        raise UnsafeRestore('Project directory missing')
    _reject_existing_symlinks(data_dir)

    # All work happens on the same filesystem as data, BEFORE the brief switch.
    with tempfile.TemporaryDirectory(prefix='.valbrick-restore-', dir=data_dir.parent) as tmp:
        temporary = Path(tmp)
        unpack_dir = temporary / 'unpacked'
        unpack_dir.mkdir()
        manifest = validate_archive(archive_path, unpack_dir, edition)
        print('Preflight OK:', edition, 'phase', manifest['phase_at_backup'],
              '->', manifest['target_phase'])

        stage = temporary / 'data'
        old_stat = data_dir.stat() if data_dir.exists() else None
        if data_dir.exists():
            shutil.copytree(data_dir, stage)
        else:
            stage.mkdir()
        db_dest = stage / 'db' / 'app.sqlite'
        db_dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(unpack_dir / 'database.sqlite3', db_dest)
        for suffix in ('-wal', '-shm', '-journal'):
            (db_dest.parent / (db_dest.name + suffix)).unlink(missing_ok=True)
        for name in ('declarations', 'exports'):
            dest = stage / name
            if dest.exists():
                shutil.rmtree(dest)
            source = unpack_dir / name
            if source.is_dir():
                shutil.copytree(source, dest)
            else:
                dest.mkdir()
        (stage / 'backups').mkdir(exist_ok=True)

        # Make sure root-owned recovery container can preserve ownership of the
        # non-root 10001 runtime user, including the new SQLite and PDF files.
        if old_stat and os.geteuid() == 0:
            for path in [stage, *stage.rglob('*')]:
                os.chown(path, old_stat.st_uid, old_stat.st_gid, follow_symlinks=False)
        if old_stat is None and os.geteuid() == 0:
            for path in [stage, *stage.rglob('*')]:
                os.chown(path, 10001, 10001, follow_symlinks=False)
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        previous = data_dir.parent / f'data.pre-restore-{stamp}'
        if previous.exists():
            raise UnsafeRestore('Recovery directory collision')
        _activate(stage, data_dir, previous, simulate_failure=simulate_failure)
        return previous if old_stat else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', required=True, type=Path)
    parser.add_argument('--data-dir', required=True, type=Path)
    parser.add_argument('--edition', required=True, choices=sorted(PHASES))
    parser.add_argument('--confirm', required=True)
    args = parser.parse_args()
    if args.confirm != 'RESTORE_OFFLINE':
        parser.error('Explicit --confirm RESTORE_OFFLINE required (stop app and scheduler first)')
    try:
        previous = restore(args.archive, args.data_dir, args.edition)
    except (OSError, UnsafeRestore) as exc:
        print('RESTORE FAILED; no new data installed:', exc)
        return 1
    print('RESTORE OK; previous data preserved at:', previous or '(no previous data)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
