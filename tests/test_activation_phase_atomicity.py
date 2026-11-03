"""Structural regression checks for the activation transaction boundary."""
import ast
import unittest
from pathlib import Path


class ActivationPhaseAtomicityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = Path(__file__).resolve().parents[1] / 'app/services/campaign_activation.py'
        cls.tree = ast.parse(source.read_text(encoding='utf-8'))
        cls.function = next(n for n in cls.tree.body if isinstance(n, ast.FunctionDef)
                            and n.name == 'activate_prepared_draft')

    def test_phase_is_created_without_implicit_commit(self):
        calls = [n for n in ast.walk(self.function) if isinstance(n, ast.Call)]
        self.assertTrue(any(isinstance(n.func, ast.Attribute) and n.func.attr == 'add'
                            and any(isinstance(a, ast.Call) and isinstance(a.func, ast.Name)
                                    and a.func.id == 'Config' for a in n.args) for n in calls))
        self.assertFalse(any(isinstance(n.func, ast.Attribute) and n.func.attr == 'set'
                             and isinstance(n.func.value, ast.Name) and n.func.value.id == 'Config'
                             for n in calls))

    def test_commit_and_rollback_are_in_same_guarded_block(self):
        blocks = [n for n in ast.walk(self.function) if isinstance(n, ast.Try)]
        self.assertTrue(any(any(isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
                                     and c.func.attr == 'commit' for node in b.body for c in ast.walk(node))
                            and any(isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
                                    and c.func.attr == 'rollback' for h in b.handlers for c in ast.walk(h))
                            for b in blocks))
