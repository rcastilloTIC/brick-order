"""Source-level safety contract runnable without the Flask environment.

These checks complement, but do not replace, web and database integration tests.
"""
from pathlib import Path
import re
import unittest

SOURCE = (Path(__file__).resolve().parents[1] / 'app/main/routes.py').read_text()


class AnnualDataSafetyContract(unittest.TestCase):
    def test_annual_clean_endpoint_fails_closed(self):
        block = SOURCE.split('def clean_data():', 1)[1].split('\n@main_bp.route', 1)[0]
        self.assertIn('abort(409', block)
        self.assertLess(block.find('abort(409'), block.find('_purge_current_cycle_data()') if '_purge_current_cycle_data()' in block else len(block))

    def test_disabling_test_mode_never_purges_campaign(self):
        block = SOURCE.split('def toggle_test_mode():', 1)[1].split('\n@main_bp.route', 1)[0]
        self.assertNotIn('_purge_current_cycle_data()', block)

    def test_money_settings_reject_non_finite_values(self):
        block = SOURCE.split('def manage_limits():', 1)[1]
        self.assertIn('minimum.is_finite()', block)
        self.assertIn('ceiling.is_finite()', block)


if __name__ == '__main__':
    unittest.main()
