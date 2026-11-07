"""Executable checks for final export snapshots, without Flask dependencies."""
import ast
from pathlib import Path
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "app/services/order_exports.py"


def functions():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    names = {"_summary_fingerprint", "assert_current_export_summary"}
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    from decimal import Decimal
    namespace = {"Decimal": Decimal}
    exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])), str(SOURCE), "exec"), namespace)
    return namespace


class Product:
    def __init__(self, id):
        self.id = id
        self.price = 1.25
        self.reference = str(id)


def snapshot(rows):
    products = {}
    people = {}
    for user, product, quantity in rows:
        people.setdefault(user, {"lines": []})["lines"].append({"product": Product(product), "quantity": quantity})
        products[product] = products.get(product, 0) + quantity
    return {"products": [{"product": Product(pid), "total_quantity": qty}
                         for pid, qty in products.items()], "participants": people}


class ExportSnapshotTests(unittest.TestCase):
    def test_same_snapshot_in_different_order(self):
        validate = functions()["assert_current_export_summary"]
        validate(snapshot([(1, 10, 50), (2, 10, 20), (1, 11, 7)]),
                 snapshot([(1, 11, 7), (2, 10, 20), (1, 10, 50)]))

    def test_reject_outdated_quantity(self):
        with self.assertRaises(ValueError):
            functions()["assert_current_export_summary"](
                snapshot([(1, 10, 50)]), snapshot([(1, 10, 70)]))

    def test_reject_changed_participant_with_same_total(self):
        with self.assertRaises(ValueError):
            functions()["assert_current_export_summary"](
                snapshot([(1, 10, 50), (2, 10, 20)]),
                snapshot([(1, 10, 40), (2, 10, 30)]))

    def test_reject_price_change(self):
        old = snapshot([(1, 10, 50)])
        current = snapshot([(1, 10, 50)])
        current["products"][0]["product"].price = 2.50
        with self.assertRaises(ValueError):
            functions()["assert_current_export_summary"](old, current)

    def test_reject_inconsistent_product_total(self):
        wrong = snapshot([(1, 10, 50)])
        wrong["products"][0]["total_quantity"] = 70
        with self.assertRaises(ValueError):
            functions()["_summary_fingerprint"](wrong)

    def test_export_checks_freshness_before_writing(self):
        text = SOURCE.read_text(encoding="utf-8")
        tree = ast.parse(text)
        fn = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                  and node.name == "generate_order_files")
        body = ast.get_source_segment(text, fn)
        assert body is not None
        self.assertLess(body.index("assert_current_export_summary("), body.index("_write_excel("))
        self.assertLess(body.index("assert_selected_commitments_materialized()"),
                        body.index("assert_current_export_summary("))


if __name__ == "__main__":
    unittest.main()
