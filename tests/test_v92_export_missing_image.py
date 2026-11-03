"""Regression: a missing LEGO image must never block final-order PDF creation.

The earlier hard-coded PNG had a corrupt IDAT stream. This exercises fpdf2's
real image decoder rather than merely checking the PNG filename/signature.
"""
from pathlib import Path
import tempfile
import unittest

from fpdf import FPDF
from PIL import Image

from app.services.order_exports import _create_placeholder_image


class MissingProductImageExportTests(unittest.TestCase):
    def test_placeholder_is_a_decodable_png_and_fpdf_can_render_it(self):
        with tempfile.TemporaryDirectory(prefix='valbrick-v92-image-') as folder:
            created = []
            try:
                filename = _create_placeholder_image(created)
                self.assertEqual(created, [filename])
                with Image.open(filename) as png:
                    self.assertEqual(png.format, 'PNG')
                    png.verify()
                pdf = FPDF()
                pdf.add_page()
                pdf.image(filename, x=10, y=10, w=24)
                result = pdf.output()
                self.assertTrue(bytes(result).startswith(b'%PDF'))
            finally:
                for filename in created:
                    Path(filename).unlink(missing_ok=True)


if __name__ == '__main__':
    unittest.main()
