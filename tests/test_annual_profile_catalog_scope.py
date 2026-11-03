import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class AnnualProfileCatalogScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.auth = (ROOT / "app/auth/routes.py").read_text()
        cls.main = (ROOT / "app/main/routes.py").read_text()
        ast.parse(cls.auth)
        ast.parse(cls.main)

    def test_profile_votes_filter_both_campaigns(self):
        section = self.auth.split("def _collect_profile_votes(", 1)[1].split("\n@auth_bp.route", 1)[0]
        self.assertIn("UserVote.campaign_id == active_campaign_id()", section)
        self.assertIn("Product.campaign_id == active_campaign_id()", section)
        self.assertIn(".join(Product,", section)

    def test_catalog_facets_are_campaign_scoped(self):
        names = ["_build_color_overview", "_get_distinct_main_group_tops", "_get_distinct_main_groups", "_get_distinct_main_group_subs", "_get_distinct_colours"]
        for name in names:
            with self.subTest(name=name):
                segment = self.main.split("def " + name + "(", 1)[1].split("\ndef ", 1)[0]
                self.assertIn("Product.campaign_id == active_campaign_id()", segment)


if __name__ == "__main__":
    unittest.main()
