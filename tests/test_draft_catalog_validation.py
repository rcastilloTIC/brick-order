"""Run the actual pure catalog validator without requiring Flask."""
import ast
import math
import unittest
from pathlib import Path

source = Path(__file__).resolve().parents[1] / 'app/services/draft_catalog_import.py'
tree = ast.parse(source.read_text())
validator = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'validate_draft_catalog_rows')
allowed = next(n for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'ALLOWED_CATALOG_FIELDS' for t in n.targets))
namespace = {'isfinite': math.isfinite}
exec(compile(ast.Module(body=[allowed, validator], type_ignores=[]), str(source), 'exec'), namespace)
validate = namespace['validate_draft_catalog_rows']


class DraftCatalogValidationTests(unittest.TestCase):
    def test_valid_catalog(self):
        validate({'3001': {'name': 'Ladrillo', 'price': 0.15, 'reference': '3001'}, '3002': {'name': 'Placa', 'price': 0}})

    def test_invalid_prices(self):
        for price in (True, float('nan'), float('inf'), -1, '1.2'):
            with self.subTest(price=price), self.assertRaises(ValueError):
                validate({'3001': {'name': 'Ladrillo', 'price': price}})

    def test_duplicate_references_case_insensitive(self):
        with self.assertRaises(ValueError):
            validate({'ABC': {'name': 'Uno'}, 'abc': {'name': 'Dos'}})

    def test_invalid_reference_or_fields(self):
        for rows in ({' A ': {'name': 'Uno'}}, {'A': None}, {'A': {'name': ' '}}, {'A': {'name': 'Uno', 'untrusted': 1}}):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                validate(rows)

    def test_product_column_lengths(self):
        for reference, fields in (
            ('R' * 101, {'name': 'Nombre'}),
            ('R', {'name': 'N' * 256}),
            ('R', {'colour_id': 'C' * 51, 'name': 'Nombre'}),
            ('R', {'image_url': 'u' * 256, 'name': 'Nombre'}),
            ('R', {'main_group': 'G' * 101, 'name': 'Nombre'}),
        ):
            with self.subTest(reference=reference, fields=fields), self.assertRaises(ValueError):
                validate({reference: fields})

    def test_invalid_field_types(self):
        for fields in (
            {'name': 'Nombre', 'is_locked': 'false'},
            {'name': 'Nombre', 'present_in_2024': 1},
            {'name': 'Nombre', 'present_in_2025': None},
            {'name': 'Nombre', 'image_url': 123},
        ):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                validate({'R': fields})

    def test_empty_catalog(self):
        with self.assertRaises(ValueError):
            validate({})


if __name__ == '__main__':
    unittest.main()
