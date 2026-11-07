"""Guard the WSGI bootstrap from falling back to debug mode."""
import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ProductionBootstrapTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "run.py").read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)

    def test_default_is_production(self):
        self.assertIn("os.getenv('FLASK_ENV', 'production')", self.source)

    def test_rejects_unknown_environment(self):
        self.assertIn("if env not in {'production', 'development'}:", self.source)
        self.assertIn("raise RuntimeError('FLASK_ENV must be production or development')", self.source)

    def test_only_explicit_development_selects_debug_config(self):
        self.assertIn("DevelopmentConfig if env == 'development' else ProductionConfig", self.source)


if __name__ == "__main__":
    unittest.main()
