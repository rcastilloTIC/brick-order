"""Static regression checks for the fail-closed ORM deletion guard.

Runtime SQLAlchemy transaction tests remain necessary before production release.
"""
import ast
from pathlib import Path
import unittest


MODEL = Path(__file__).resolve().parents[1] / 'app' / 'models.py'


class HistoricalOrderParentDeletionTests(unittest.TestCase):
    def test_guard_is_registered_for_before_flush(self):
        tree = ast.parse(MODEL.read_text())
        functions = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
        self.assertIn('_protect_order_parents_from_deletion', functions)
        function = functions['_protect_order_parents_from_deletion']
        decorators = [ast.unparse(d) for d in function.decorator_list]
        self.assertIn("event.listens_for(Session, 'before_flush')", decorators)

    def test_guard_checks_both_foreign_keys(self):
        tree = ast.parse(MODEL.read_text())
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                        and n.name == '_protect_order_parents_from_deletion')
        source = ast.unparse(function)
        for target in ('isinstance(obj, User)', 'isinstance(obj, Product)',
                       'Order.user_id == obj.id', 'Order.product_id == obj.id',
                       'raise ValueError'):
            self.assertIn(target, source)


if __name__ == '__main__':
    unittest.main()
