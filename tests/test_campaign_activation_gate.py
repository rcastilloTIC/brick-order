"""Source-level safety checks runnable without Flask dependencies."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

class ActivationGateTests(unittest.TestCase):
    def test_release_flag_and_confirmation_precede_mutation(self):
        source = (ROOT / 'app/services/campaign_activation.py').read_text()
        tree = ast.parse(source)
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'activate_prepared_draft')
        code = ast.get_source_segment(source, fn)
        self.assertLess(code.index('ENABLE_ANNUAL_ACTIVATION'), code.index('UPDATE campaign SET status'))
        self.assertLess(code.index('confirmation !='), code.index('UPDATE campaign SET status'))
        self.assertLess(code.index('inspect_annual_readiness()'), code.index('UPDATE campaign SET status'))

    def test_admin_route_requires_login_and_admin(self):
        source = (ROOT / 'app/main/routes.py').read_text()
        section = source.split('def campaign_activate():', 1)[1].split('\n\n@main_bp.route', 1)[0]
        self.assertIn('_ensure_admin()', section)
        self.assertIn('activate_prepared_draft(', section)
        self.assertIn('confirmation=request.form.get(', section)

if __name__ == '__main__': unittest.main()
