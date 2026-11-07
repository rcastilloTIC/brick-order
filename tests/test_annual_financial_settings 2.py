import importlib.util
import pathlib
import sys
import types
import unittest
from unittest.mock import Mock

FILE = pathlib.Path(__file__).resolve().parents[1] / "app/services/campaign_settings.py"


class AnnualSettingTests(unittest.TestCase):
    def setUp(self):
        self.saved = {name: sys.modules.get(name) for name in (
            "app", "app.models", "app.services", "app.services.active_campaign")}
        app = types.ModuleType("app"); app.__path__ = []
        services = types.ModuleType("app.services"); services.__path__ = []
        models = types.ModuleType("app.models")
        self.cfg = {}
        models.Config = types.SimpleNamespace(get=lambda key: self.cfg.get(key), set=lambda key, val: self.cfg.__setitem__(key,val))
        models.Campaign = types.SimpleNamespace(query=types.SimpleNamespace(limit=lambda n: types.SimpleNamespace(count=lambda: self.count)))
        active = types.ModuleType("app.services.active_campaign")
        active.current_campaign = lambda: self.campaign
        sys.modules.update({"app":app,"app.models":models,"app.services":services,"app.services.active_campaign":active})
        spec = importlib.util.spec_from_file_location("annual_settings_under_test", FILE)
        self.module = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.module)
        self.count = 1; self.campaign = types.SimpleNamespace(id=1)

    def tearDown(self):
        for name, old in self.saved.items():
            if old is None: sys.modules.pop(name,None)
            else: sys.modules[name] = old

    def test_legacy_single_campaign(self):
        self.cfg['final_order_excel'] = 'old.xlsx'
        self.assertEqual(self.module.get_annual_setting('final_order_excel'), 'old.xlsx')

    def test_previous_year_does_not_leak(self):
        self.cfg['final_order_excel'] = 'old.xlsx'
        self.count = 2; self.campaign = types.SimpleNamespace(id=2)
        self.assertIsNone(self.module.get_annual_setting('final_order_excel'))
        self.module.set_annual_setting('final_order_excel','new.xlsx')
        self.assertEqual(self.cfg['annual_2_final_order_excel'],'new.xlsx')
        self.assertEqual(self.cfg['final_order_excel'],'old.xlsx')

    def test_two_years_isolated(self):
        self.count = 2
        self.module.set_annual_setting('order_shipping_amount', '40')
        self.campaign = types.SimpleNamespace(id=2)
        self.assertIsNone(self.module.get_annual_setting('order_shipping_amount'))
        self.module.set_annual_setting('order_shipping_amount', '70')
        self.campaign = types.SimpleNamespace(id=1)
        self.assertEqual(self.module.get_annual_setting('order_shipping_amount'),'40')

    def test_no_active_campaign_rejects_writes(self):
        self.campaign = None
        with self.assertRaises(ValueError): self.module.set_annual_setting('final_order_excel','bad')

    def test_allowlist(self):
        with self.assertRaises(ValueError): self.module.annual_key('password',1)
        with self.assertRaises(ValueError): self.module.annual_key('final_order_excel',True)

if __name__ == '__main__': unittest.main()
