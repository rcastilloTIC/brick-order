import importlib.util
import tempfile
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "app/services/export_path_safety.py"
spec = importlib.util.spec_from_file_location("export_path_safety", MODULE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class ExportPathTests(unittest.TestCase):
    def test_valid_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "order.xlsx"
            p.write_bytes(b"data")
            self.assertEqual(mod.safe_export_path(d, "order.xlsx", suffix=".xlsx"), p.resolve())
            self.assertIsNone(mod.safe_export_path(d, "order.xlsx", suffix=".pdf"))

    def test_traversal_and_absolute_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(mod.safe_export_path(d, "../secret.xlsx"))
            self.assertIsNone(mod.safe_export_path(d, "/tmp/secret.xlsx"))
            self.assertIsNone(mod.safe_export_path(d, "..\\secret.xlsx"))

    def test_external_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as outside:
            target = Path(outside) / "secret.zip"
            target.write_bytes(b"data")
            (Path(d) / "export.zip").symlink_to(target)
            self.assertIsNone(mod.safe_export_path(d, "export.zip", suffix=".zip"))

    def test_no_physical_deletion_on_reset(self):
        source=(MODULE.parents[1] / "main/routes.py").read_text()
        block=source.split("def _reset_order_exports_state()", 1)[1].split("def _clear_declaration_files",1)[0]
        self.assertNotIn("os.remove",block)
        self.assertIn('set_annual_setting(key, "")',block)


if __name__ == "__main__":
    unittest.main()
