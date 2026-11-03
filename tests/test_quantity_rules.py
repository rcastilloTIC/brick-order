import unittest
from importlib.util import spec_from_file_location, module_from_spec
from pathlib import Path

source = Path(__file__).resolve().parents[1] / 'app/services/quantity_rules.py'
spec = spec_from_file_location('quantity_rules_isolated', source)
module = module_from_spec(spec)
spec.loader.exec_module(module)
validate_quantity = module.validate_quantity


class QuantityRuleTests(unittest.TestCase):
    def test_existing_tiers(self):
        self.assertTrue(validate_quantity('1.35', 25)[0])
        self.assertTrue(validate_quantity('1.36', 10)[0])
        self.assertFalse(validate_quantity('1.35', 10)[0])
        self.assertFalse(validate_quantity('1.36', 25)[0])

    def test_reject_invalid_values(self):
        for price in (None, 'nan', 'inf', '-1', 'bad'):
            self.assertFalse(validate_quantity(price, 25)[0])
        for quantity in (-25, 0, True, 1.5, 26):
            self.assertFalse(validate_quantity('1.35', quantity)[0])

    def test_configurable_rules(self):
        options = dict(low_price_max='2', low_price_min=50, low_price_step=25,
                       high_price_min=1, high_price_step=1)
        self.assertTrue(validate_quantity('0.40', 75, **options)[0])
        self.assertFalse(validate_quantity('0.40', 25, **options)[0])
        self.assertTrue(validate_quantity('3', 1, **options)[0])
