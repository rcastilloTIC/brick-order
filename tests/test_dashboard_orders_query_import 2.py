"""Regresion: dashboard debe importar el query de pedidos por campana."""
import ast
import unittest
from pathlib import Path


class DashboardOrdersQueryImportTest(unittest.TestCase):
    def test_dashboard_imports_campaign_scoped_orders_query(self):
        path = Path(__file__).resolve().parents[1] / "app" / "main" / "routes.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = [node for node in tree.body if isinstance(node, ast.ImportFrom)
                   and node.module == "app.services.campaign_data"]
        self.assertTrue(imports)
        self.assertIn("orders_query", {alias.name for node in imports for alias in node.names})
        funcs = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "user_dashboard"]
        self.assertEqual(len(funcs), 1)
        self.assertTrue(any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                            and node.func.id == "orders_query" for node in ast.walk(funcs[0])))


if __name__ == "__main__":
    unittest.main()
