"""Regression checks for annual selection and financial limits."""
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

class AnnualLimitsIsolationTests(unittest.TestCase):
    def test_all_three_limits_use_annual_settings(self):
        content = (ROOT / "app/main/routes.py").read_text()
        settings = (ROOT / "app/services/campaign_settings.py").read_text()
        for key in ("limit_minimum_total", "limit_phase_one_order_limit", "limit_final_selection_limit"):
            self.assertIn(f'"{key}"', settings)
            self.assertIn(f"set_annual_setting('{key}'", content)
            self.assertIn(f"get_annual_setting('{key}'", content)
            self.assertNotIn(f"Config.set('{key}'", content)
            self.assertNotIn(f"Config.get('{key}'", content)

    def test_no_legacy_fallback_with_multiple_campaigns(self):
        content = (ROOT / "app/services/campaign_settings.py").read_text()
        self.assertIn("Campaign.query.limit(2).count() == 1", content)
        self.assertIn("return None", content)

if __name__ == '__main__':
    unittest.main()
