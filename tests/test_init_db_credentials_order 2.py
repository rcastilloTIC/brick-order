"""Regression: invalid credentials must not mutate the database."""
import ast
from pathlib import Path
import unittest


class InitDbCredentialsOrderTest(unittest.TestCase):
    def test_admin_password_is_validated_before_schema_changes(self):
        source = Path(__file__).resolve().parents[1] / 'app' / '__init__.py'
        module = ast.parse(source.read_text(encoding='utf-8'))
        fn = next(n for n in module.body if isinstance(n, ast.FunctionDef) and n.name == 'init_db')
        calls = [(n.lineno, ast.unparse(n.func)) for n in ast.walk(fn) if isinstance(n, ast.Call)]
        first_schema = min(line for line, name in calls if name in ('db.create_all', '_ensure_schema'))
        checks = [n for n in ast.walk(fn) if isinstance(n, ast.If) and
                  any(isinstance(x, ast.Raise) for x in ast.walk(n)) and
                  'admin_password' in ast.unparse(n.test)]
        self.assertEqual(len(checks), 1)
        self.assertLess(checks[0].lineno, first_schema)
        self.assertTrue(all(isinstance(n, (ast.Expr, ast.Assign, ast.If, ast.ImportFrom))
                            for n in fn.body), 'Unexpected init_db statement needs review')


if __name__ == '__main__':
    unittest.main()
