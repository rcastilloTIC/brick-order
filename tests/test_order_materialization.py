import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[1] / 'app/services/order_materialization.py'
# Test the actual planner without requiring Flask/database dependencies.
source = path.read_text(encoding='utf-8')
import ast
node = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == 'missing_order_floors')
module = ast.Module(body=[node], type_ignores=[])
namespace = {'defaultdict': __import__('collections').defaultdict}
exec(compile(module, str(path), 'exec'), namespace)
plan = namespace['missing_order_floors']

class TestMaterialization(unittest.TestCase):
    def test_selected_only(self):
        self.assertEqual(plan([(1, 1, 50), (1, 2, 25)], [], {1}), {(1, 1): 50})
    def test_partial_existing_order(self):
        self.assertEqual(plan([(1, 1, 50)], [(1, 1, 20)], {1}), {(1, 1): 30})
    def test_idempotent(self):
        votes = [(1, 1, 50)]
        self.assertEqual(plan(votes, [(1, 1, 50)], {1}), {})
    def test_aggregate_several_order_rows(self):
        self.assertEqual(plan([(1, 1, 50)], [(1, 1, 15), (1, 1, 20)], {1}), {(1, 1): 15})
    def test_multiple_users(self):
        self.assertEqual(plan([(1, 1, 7), (2, 1, 9)], [], {1}), {(1, 1): 7, (2, 1): 9})
    def test_does_not_decrease_orders(self):
        self.assertEqual(plan([(1, 1, 10)], [(1, 1, 20)], {1}), {})
    def test_reject_invalid_quantities(self):
        with self.assertRaises(ValueError):
            plan([(1, 1, 0)], [], {1})
        with self.assertRaises(ValueError):
            plan([(1, 1, 5)], [(1, 1, -1)], {1})

if __name__ == '__main__':
    unittest.main()
