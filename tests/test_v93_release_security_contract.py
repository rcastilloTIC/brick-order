"""Pure-source tests of release defaults; runtime verified in Docker separately."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_no_direct_public_port_and_nonroot_runtime():
    compose = (ROOT / 'docker-compose.yml').read_text()
    dockerfile = (ROOT / 'Dockerfile').read_text()
    assert re.search(r'127\.0\.0\.1:\$\{PORT:-\d+\}:5001', compose)
    assert 'USER valbrick' in dockerfile
    assert '--uid 10001' in dockerfile
    assert 'ENTRYPOINT ["sh", "/app/docker-entrypoint.sh"]' in dockerfile


def test_online_restore_disabled_and_offline_has_rollback():
    routes = (ROOT / 'app/main/routes.py').read_text()
    assert 'def restore_backup_endpoint():' in routes
    restore = routes.split('def restore_backup_endpoint():', 1)[1].split('@main_bp.route(', 1)[0]
    assert 'abort(409' in restore
    assert 'restore_backup(temp_file' not in restore
    offline = (ROOT / 'scripts/restore_offline.py').read_text()
    for check in ('PRAGMA integrity_check', 'PRIVATE_TABLES', 'archive.testzip()',
                  'os.replace(destination, previous)', 'os.replace(previous, destination)'):
        assert check in offline


def test_agpl_visible_source_link_and_repo_hygiene():
    assert (ROOT / 'EDITION').read_text().strip() in ('PUBLICA', 'EXTENDED')
    assert 'SOURCE_CODE_URL' in (ROOT / 'config.py').read_text()
    assert 'source_code_url' in (ROOT / 'templates/base.html').read_text()
    assert 'AGPL-3.0-only' in (ROOT / 'NOTICE').read_text()
    for path in (ROOT / '.gitignore', ROOT / '.dockerignore'):
        src = path.read_text()
        assert 'isolated/' in src
        assert '.env' in src
        assert 'data' in src


def test_release_phase_policy():
    routes = (ROOT / 'app/main/routes.py').read_text()
    release = routes.split('def generate_order_exports_route():', 1)[1].split('def regenerate_order_exports_route(', 1)[0]
    assert 'get_current_phase() != "order"' in release
    assert '_order_is_finalized()' in release
    template = (ROOT / 'templates/admin_dashboard.html').read_text()
    assert 'order_action_enabled' in template
    assert "current_phase in ['final', 'order'" in template
    if (ROOT / 'EDITION').read_text().strip() == 'PUBLICA':
        assert 'class FinalExtensionInterest' not in (ROOT / 'app/models.py').read_text()
        assert 'def final_extension_close_order' not in routes
    else:
        assert 'class FinalExtensionInterest' in (ROOT / 'app/models.py').read_text()
        assert "set_annual_setting('final_extension_closed', '1')" in routes
