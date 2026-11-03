"""Regression guard for the order export source switch."""
import ast
from pathlib import Path
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "app/services/order_exports.py"

class OrderExportSourceTests(unittest.TestCase):
    def test_both_models_are_scoped_to_campaign(self):
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn('quantity_model = Order if use_orders else UserVote', source)
        self.assertIn('quantity_model.campaign_id == active_campaign_id()', source)
        self.assertIn('quantity_model.product_id.in_(product_map.keys())', source)

    def test_post_selection_exports_use_orders(self):
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "build_final_order_context")
        choices = [n for n in ast.walk(fn) if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "use_orders" for t in n.targets)]
        self.assertEqual(len(choices), 1)
        phases = ast.literal_eval(choices[0].value.comparators[0])
        edition = (SOURCE.parents[2] / 'VALBRICK_EDITION').read_text(encoding='ascii').strip()
        self.assertIn(edition, {'publica', 'extended'})
        self.assertEqual(phases, {'order', 'final_extension'} if edition == 'extended' else {'order'})

if __name__ == "__main__":
    unittest.main()
