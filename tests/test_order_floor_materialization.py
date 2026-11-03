import importlib.util
import unittest
from pathlib import Path

_path = Path(__file__).resolve().parents[1] / "app/services/commitment_ledger.py"
_spec = importlib.util.spec_from_file_location("standalone_commitment_ledger", _path)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
materialized_order_quantity = _module.materialized_order_quantity
effective_commitment = _module.effective_commitment

class OrderFloorTests(unittest.TestCase):
    def test_first_order_includes_selected_vote(self):
        self.assertEqual(materialized_order_quantity([], [(1, "0.50", 50)], product_id=1, additional_quantity=10), 60)
    def test_partial_existing_order_fills_gap(self):
        self.assertEqual(materialized_order_quantity([(1, "0.50", 15)], [(1, "0.50", 50)], product_id=1, additional_quantity=10), 45)
    def test_no_duplicate_floor(self):
        self.assertEqual(materialized_order_quantity([(1, "0.50", 50)], [(1, "0.50", 50)], product_id=1, additional_quantity=10), 10)
    def test_rejected_votes_do_not_transfer(self):
        self.assertEqual(materialized_order_quantity([], [(2, "1.00", 45)], product_id=1, additional_quantity=10), 10)
    def test_ledger_matches_materialized_order(self):
        from decimal import Decimal
        expected = effective_commitment([], [(1, "0.50", 50), (2, "1.00", 40)],
            phase="order", selected_product_ids={1}, additional=(1, "0.50", 10))
        stored = materialized_order_quantity([], [(1, "0.50", 50)], product_id=1, additional_quantity=10)
        self.assertEqual(expected, Decimal("0.50") * stored)
    def test_invalid_increments_fail(self):
        for value in (-1, 0, True, 1.5):
            with self.assertRaises(ValueError):
                materialized_order_quantity([], [], product_id=1, additional_quantity=value)

if __name__ == "__main__": unittest.main()
