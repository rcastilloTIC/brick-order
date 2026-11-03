"""Deployment configuration regression tests; do not require Docker daemon."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def test_compose_does_not_force_insecure_session_cookie():
    compose = (ROOT / "docker-compose.yml").read_text()
    assert 'SESSION_COOKIE_SECURE: "${SESSION_COOKIE_SECURE:-true}"' in compose
    assert not re.search(r'SESSION_COOKIE_SECURE:\s*["\']?false', compose, re.I)


def test_docker_build_excludes_secrets_and_persistent_data():
    ignore = set((ROOT / ".dockerignore").read_text().splitlines())
    assert {".env", "data", ".git", ".venv"} <= ignore


def test_production_configuration_defaults_to_secure_cookie():
    config = (ROOT / "config.py").read_text()
    assert 'SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "true")' in config
