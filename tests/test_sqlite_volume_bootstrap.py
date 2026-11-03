"""Regression tests for persistent SQLite directory bootstrap."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SQLiteVolumeBootstrapTests(unittest.TestCase):
    def test_compose_database_uses_persistent_nested_directory(self):
        compose = (ROOT / 'docker-compose.yml').read_text()
        self.assertIn('DATABASE_URL: sqlite:////data/db/app.sqlite', compose)
        self.assertIn('./data:/data', compose)

    def test_docker_entrypoint_executes_command_and_creates_directory(self):
        dockerfile = (ROOT / 'Dockerfile').read_text()
        self.assertIn('ENTRYPOINT ["sh", "/app/docker-entrypoint.sh"]', dockerfile)
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory) / 'volume'
            env = {**os.environ, 'BOM_DATA_DIR': str(data)}
            command = ['sh', str(ROOT / 'docker-entrypoint.sh'), sys.executable,
                       '-c', 'print("ready")']
            result = subprocess.run(command, capture_output=True, text=True,
                                    env=env, check=True)
            self.assertEqual(result.stdout.strip(), 'ready')
            self.assertTrue((data / 'db').is_dir())

    def test_existing_database_file_is_not_modified(self):
        with tempfile.TemporaryDirectory() as directory:
            dbdir = Path(directory) / 'db'
            dbdir.mkdir()
            database = dbdir / 'app.sqlite'
            database.write_bytes(b'existing-database')
            env = {**os.environ, 'BOM_DATA_DIR': directory}
            subprocess.run(['sh', str(ROOT / 'docker-entrypoint.sh'),
                            sys.executable, '-c', 'pass'], env=env, check=True)
            self.assertEqual(database.read_bytes(), b'existing-database')


if __name__ == '__main__':
    unittest.main()
