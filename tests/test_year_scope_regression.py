"""Regression checks for historical campaign bleed-through in sensitive queries.

These inspect source contracts because Flask dependencies are not available in
all offline CI environments. They must be complemented by HTTP/SQL tests.
"""
from pathlib import Path
import ast
import unittest

SOURCE = (Path(__file__).resolve().parents[1] / 'app/main/routes.py').read_text()
TREE = ast.parse(SOURCE)

def function_body(name):
    node = next(n for n in TREE.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)
    return ast.get_source_segment(SOURCE, node)

class AnnualQueryBoundaryTests(unittest.TestCase):
    def test_reference_limits_are_year_scoped(self):
        body = function_body('submit_vote') if any(isinstance(n,ast.FunctionDef) and n.name=='submit_vote' for n in TREE.body) else SOURCE
        self.assertIn('UserVote.user_id == current_user.id, UserVote.campaign_id == active_campaign_id()', body)

    def test_catalog_preview_missing_reference_rows_scoped(self):
        self.assertIn('UserVote.product_id.in_(missing_ids), UserVote.campaign_id == active_campaign_id(), Product.campaign_id == active_campaign_id()', SOURCE)

    def test_catalog_preview_changed_price_rows_scoped(self):
        self.assertIn('Product.reference.in_(price_changed_refs), UserVote.campaign_id == active_campaign_id(), Product.campaign_id == active_campaign_id()', SOURCE)

if __name__ == '__main__':
    unittest.main()
