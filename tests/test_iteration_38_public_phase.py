import ast
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PUBLIC = (ROOT / "app/main/routes.py").read_text(encoding="utf-8").find("final_extension") == -1
SOURCE = (ROOT / "app/main/routes.py").read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)

class PublicPhaseSeparationTest(unittest.TestCase):
    def test_private_models_not_imported_in_public_routes(self):
        imports = {alias.name for node in ast.walk(TREE) if isinstance(node, ast.ImportFrom) and node.module == "app.models" for alias in node.names}
        if PUBLIC:
            self.assertFalse({"ExtensionInterest", "FinalExtensionInterest"} & imports)
        else:
            self.assertTrue({"ExtensionInterest", "FinalExtensionInterest"} <= imports)

    def test_public_phase_choices_exclude_private_phases(self):
        assignments = [node for node in TREE.body if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "PHASES" for t in node.targets)]
        self.assertEqual(len(assignments), 1)
        phases = ast.literal_eval(assignments[0].value)
        if PUBLIC:
            self.assertEqual(phases, ("first", "second", "final", "order"))
        else:
            self.assertIn("extension", phases)
            self.assertIn("final_extension", phases)

    def test_public_vote_quantity_has_no_private_exception(self):
        func = next(n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == "submit_vote")
        body = ast.get_source_segment(SOURCE, func)
        if PUBLIC:
            self.assertIn("assert_nondecreasing_vote(previous_quantity, quantity)", body)
            self.assertNotIn('phase != "final_extension"', body)
            self.assertNotIn('0 if phase == "final_extension"', body)
        else:
            self.assertIn("assert_nondecreasing_vote(previous_quantity, quantity)", body)

if __name__ == "__main__":
    unittest.main()
