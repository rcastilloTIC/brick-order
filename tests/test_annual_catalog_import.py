"""Regression checks for annual catalogue upload boundaries."""
import ast
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class AnnualCatalogImportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "app/main/routes.py").read_text()
        cls.tree = ast.parse(cls.source)
        cls.functions = {n.name: n for n in ast.walk(cls.tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}

    def test_pending_preview_has_both_identities(self):
        node = self.functions["upload_data"]
        source = ast.get_source_segment(self.source, node)
        self.assertIn('"campaign_id": campaign_id', source)
        self.assertIn('"admin_id": current_user.id', source)
        self.assertIn('_pending_catalog_matches(pending, campaign_id, current_user.id)', source)
        self.assertGreaterEqual(source.count('_pending_catalog_matches('), 2)

    def test_old_previews_fail_closed(self):
        source = ast.get_source_segment(self.source, self.functions['_pending_catalog_matches'])
        self.assertIn('type(pending.get("campaign_id")) is int', source)
        self.assertIn('type(pending.get("admin_id")) is int', source)

    def test_import_checks_active_campaign_first(self):
        node = self.functions['_handle_products_excel_upload']
        first = node.body[0]
        self.assertIsInstance(first, ast.Expr)
        self.assertIsInstance(first.value, ast.Call)
        self.assertEqual(first.value.func.id, 'active_campaign_id')


if __name__ == '__main__':
    unittest.main()
