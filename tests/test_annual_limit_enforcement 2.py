"""Executable limit-service tests without Flask or SQLAlchemy dependencies."""
import importlib.util
import pathlib
import sys
import types
import unittest
from unittest.mock import patch

FILE = pathlib.Path(__file__).resolve().parents[1] / 'app/services/mode.py'

class LimitsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.saved = {key: sys.modules.get(key) for key in ('flask', 'app', 'app.models', 'app.services', 'app.services.campaign_settings')}
        flask = types.ModuleType('flask')
        flask.current_app = types.SimpleNamespace(config={'PHASE_ONE_ORDER_LIMIT': 235, 'FINAL_SELECTION_LIMIT': 85, 'MAX_REFERENCES_PER_USER': 10, 'PHASE_TWO_REFERENCE_LIMIT': 20})
        sys.modules['flask'] = flask
        sys.modules['app'] = types.ModuleType('app')
        sys.modules['app.services'] = types.ModuleType('app.services')
        models = types.ModuleType('app.models')
        models.Config = type('Config', (), {'get': staticmethod(lambda key: '999' if key.startswith('limit_') else None)})
        sys.modules['app.models'] = models
        settings = types.ModuleType('app.services.campaign_settings')
        settings.get_annual_setting = lambda key: cls.values.get(key)
        sys.modules['app.services.campaign_settings'] = settings
        spec = importlib.util.spec_from_file_location('_tested_annual_mode', FILE)
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    @classmethod
    def tearDownClass(cls):
        for key, value in cls.saved.items():
            if value is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = value

    def setUp(self):
        self.__class__.values = {}

    def test_annual_override(self):
        self.values.update(limit_phase_one_order_limit='210.50', limit_final_selection_limit='72')
        value = self.module.get_limit_configuration(test_mode=False)
        self.assertEqual(value['phase_one_order_limit'], 210.5)
        self.assertEqual(value['final_selection_limit'], 72)

    def test_no_legacy_global_leakage(self):
        value = self.module.get_limit_configuration(test_mode=False)
        self.assertEqual(value['phase_one_order_limit'], 235)
        self.assertEqual(value['final_selection_limit'], 85)

    def test_reject_invalid_values(self):
        for bad in ('nan', '-3', '0', 'Infinity'):
            with self.subTest(bad=bad):
                self.values['limit_phase_one_order_limit'] = bad
                with self.assertRaises(ValueError):
                    self.module.get_limit_configuration(test_mode=False)
        self.values.clear()
        self.values['limit_final_selection_limit'] = '12.5'
        with self.assertRaises(ValueError):
            self.module.get_limit_configuration(test_mode=False)

    def test_test_mode_remains_explicit(self):
        self.values.update(limit_phase_one_order_limit='200', limit_final_selection_limit='70')
        value = self.module.get_limit_configuration(test_mode=True)
        self.assertEqual(value['phase_one_order_limit'], 50)
        self.assertEqual(value['final_selection_limit'], 10)

if __name__ == '__main__':
    unittest.main()
