"""Actual algorithm checks (no third-party Python requirements needed)."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MATERIAL = ROOT / "app/services/order_materialization.py"
EXPORT = ROOT / "app/services/order_exports.py"


def planner():
    tree = ast.parse(MATERIAL.read_text())
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                and n.name == "missing_order_floors")
    module = ast.Module(body=[node], type_ignores=[])
    namespace = {"defaultdict": __import__("collections").defaultdict}
    exec(compile(ast.fix_missing_locations(module), str(MATERIAL), "exec"), namespace)
    return namespace["missing_order_floors"]


class ExportFloorTests(unittest.TestCase):
    def test_selected_vote_without_order_is_missing(self):
        self.assertEqual(planner()([(1, 10, 50)], [], {10}), {(1, 10): 50})

    def test_partial_orders_show_missing_amount(self):
        self.assertEqual(planner()([(1, 10, 50)], [(1, 10, 20)], {10}), {(1, 10): 30})

    def test_complete_or_increased_orders_pass(self):
        self.assertEqual(planner()([(1, 10, 50)], [(1, 10, 70)], {10}), {})

    def test_discarded_votes_do_not_block_export(self):
        self.assertEqual(planner()([(1, 10, 50), (1, 11, 80)],
                                   [(1, 10, 50)], {10}), {})

    def test_multiple_users_and_aggregated_rows(self):
        self.assertEqual(planner()([(1, 10, 30), (1, 10, 20), (2, 10, 5)],
                                   [(1, 10, 25), (1, 10, 25)], {10}),
                         {(2, 10): 5})

    def test_final_file_generation_rejects_incomplete_floors(self):
        tree = ast.parse(EXPORT.read_text())
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                  and n.name == "generate_order_files")
        calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Name)]
        self.assertTrue(any(n.func.id == "assert_selected_commitments_materialized" for n in calls))
        src = ast.get_source_segment(EXPORT.read_text(), fn)
        self.assertLess(src.index("assert_selected_commitments_materialized()"),
                        src.index("_write_excel("))


if __name__ == "__main__":
    unittest.main()
