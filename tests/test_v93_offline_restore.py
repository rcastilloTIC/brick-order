"""Stdlib-only restore checks: preflight, edition boundary, simulated crash rollback."""
from pathlib import Path
import importlib.util
import json
import sqlite3
import tempfile
import unittest
from zipfile import ZipFile

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'restore_offline.py'
spec = importlib.util.spec_from_file_location('restore_offline_tool', SCRIPT)
restore_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(restore_module)
backup_spec = importlib.util.spec_from_file_location('backup_offline_tool', SCRIPT.with_name('create_offline_backup.py'))
backup_module = importlib.util.module_from_spec(backup_spec)
backup_spec.loader.exec_module(backup_module)


def sample_database(path, edition):
    with sqlite3.connect(path) as con:
        for name in restore_module.REQUIRED_TABLES:
            if name == 'campaign':
                con.execute('CREATE TABLE campaign (id INTEGER, status TEXT)')
                con.execute("INSERT INTO campaign VALUES (10,'legacy_active')")
            elif name == 'config':
                con.execute('CREATE TABLE config (key TEXT, value TEXT)')
                con.execute("INSERT INTO config VALUES ('phase_campaign_10','order')")
            else:
                con.execute(f'CREATE TABLE "{name}" (id INTEGER)')
        if edition == 'EXTENDED':
            for name in restore_module.PRIVATE_TABLES:
                con.execute(f'CREATE TABLE "{name}" (id INTEGER)')
        con.execute('INSERT INTO "order" VALUES (777)')


def sample_zip(path, edition, *, unsafe=False, bad_phase=False):
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / 'orig.sqlite'
        sample_database(db, edition)
        manifest = dict(version=1, db_filename='database.sqlite3', edition=edition,
                        paths={'declarations': 'declarations', 'exports': 'exports'},
                        phase_at_backup='order',
                        target_phase=('invalid' if bad_phase else 'order'))
        with ZipFile(path, 'w') as z:
            z.writestr('manifest.json', json.dumps(manifest))
            z.write(db, 'database.sqlite3')
            z.writestr('declarations/signature.pdf', b'%PDF-1.4\n')
            z.writestr('exports/final.xlsx', b'EXAMPLE')
            if unsafe:
                z.writestr('../outside.txt', 'wrong')


class OfflineReleaseRestoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.edition = (Path(__file__).resolve().parents[1] / 'EDITION').read_text().strip()
        self.data = self.root / 'data'
        self.data.mkdir()
        (self.data / 'db').mkdir()
        (self.data / 'declarations').mkdir()
        (self.data / 'declarations' / 'existing.pdf').write_bytes(b'old')
        (self.data / 'exports').mkdir()
        (self.data / 'exports' / 'existing.xlsx').write_bytes(b'old_excel')
        (self.data / 'backups').mkdir()
        sample_database(self.data / 'db' / 'app.sqlite', self.edition)
        self.archive = self.root / 'archive.zip'
        sample_zip(self.archive, self.edition)

    def test_create_offline_zip_and_restore(self):
        output = self.root / 'fresh.zip'
        backup_module.backup(self.data, output, self.edition)
        self.assertTrue(output.is_file())
        with ZipFile(output) as z:
            self.assertIsNone(z.testzip())
            self.assertEqual(json.loads(z.read('manifest.json'))['edition'], self.edition)
        previous = restore_module.restore(output, self.data, self.edition)
        self.assertTrue(previous.is_dir())
        self.assertEqual((self.data / 'declarations' / 'existing.pdf').read_bytes(), b'old')
        self.assertEqual((self.data / 'exports' / 'existing.xlsx').read_bytes(), b'old_excel')

    def test_swap_and_retained_old_state(self):
        old = restore_module.restore(self.archive, self.data, self.edition)
        self.assertTrue(old.is_dir())
        self.assertEqual((old / 'declarations' / 'existing.pdf').read_bytes(), b'old')
        self.assertFalse((self.data / 'declarations' / 'existing.pdf').exists())
        self.assertEqual((self.data / 'declarations' / 'signature.pdf').read_bytes(), b'%PDF-1.4\n')
        self.assertEqual((self.data / 'exports' / 'final.xlsx').read_bytes(), b'EXAMPLE')
        self.assertEqual((self.data / 'backups').exists(), True)
        with sqlite3.connect(self.data / 'db' / 'app.sqlite') as conn:
            self.assertEqual(conn.execute('SELECT id FROM "order"').fetchone(), (777,))

    def test_mid_swap_error_restores_original_tree(self):
        with self.assertRaises(OSError):
            restore_module.restore(self.archive, self.data, self.edition, simulate_failure=True)
        self.assertEqual((self.data / 'declarations' / 'existing.pdf').read_bytes(), b'old')
        self.assertEqual((self.data / 'exports' / 'existing.xlsx').read_bytes(), b'old_excel')
        self.assertEqual(list(self.root.glob('data.pre-restore-*')), [])

    def test_zip_slip_and_bad_phase_fail_before_changes(self):
        for suffix, options in [('unsafe', {'unsafe':True}), ('phase', {'bad_phase':True})]:
            sample_zip(self.archive, self.edition, **options)
            with self.assertRaises(restore_module.UnsafeRestore, msg=suffix):
                restore_module.restore(self.archive, self.data, self.edition)
            self.assertEqual((self.data / 'declarations' / 'existing.pdf').read_bytes(), b'old')

    def test_wrong_edition_rejected(self):
        other = 'EXTENDED' if self.edition == 'PUBLICA' else 'PUBLICA'
        sample_zip(self.archive, other)
        with self.assertRaises(restore_module.UnsafeRestore):
            restore_module.restore(self.archive, self.data, self.edition)
        self.assertEqual((self.data / 'declarations' / 'existing.pdf').read_bytes(), b'old')


if __name__ == '__main__':
    unittest.main()
